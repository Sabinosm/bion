"""service_storage_pfp.py -- armazenamento de fotos de perfil (avatar).

Cuida do ciclo de vida da imagem no bucket do Supabase: valida o arquivo
pelo conteúdo, normaliza (orientação, fundo, tamanho, formato) e envia
com nome aleatório, além de montar a URL pública e remover arquivos
antigos. O cliente do Supabase é criado só quando necessário, então
operações que apenas leem a URL não exigem credenciais.
"""

import os
import io
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from supabase import create_client, Client
from src.core.exceptions import BionException, DadosInvalidosError
import logging

logger = logging.getLogger(__name__)

# Formatos aceitos no upload de avatar (identificados pelo CONTEÚDO do
# arquivo pelo Pillow, nunca pela extensão ou content-type do cliente).
FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP"}

# Teto de pixels da imagem de entrada. Uma foto de perfil nunca precisa
# de mais que isso; o limite barra "bombas de descompressão" (arquivo
# pequeno que declara dimensões gigantes e esgota a memória ao
# decodificar). Conferido sobre o cabeçalho, antes de decodificar.
MAX_PIXELS = 25_000_000

class StorageService:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL")
        self.key = os.environ.get("SUPABASE_KEY")
        self.bucket_name = os.environ.get("SUPABASE_BUCKET", "avatares")

        self._supabase = None
        self.max_size = 4 * 1024 * 1024  # 4MB

    @property
    def supabase(self) -> Client:
        """Cliente do Supabase, criado na primeira vez que é usado.

        Lazy porque o service é instanciado no import do controller e
        só upload/remoção precisam do cliente; credencial ausente só
        falha quando se tenta mexer no storage.

        Levanta:
            ValueError: se SUPABASE_URL ou SUPABASE_KEY não estiverem
                definidas.
        """
        if self._supabase is None:
            if not self.url or not self.key:
                raise ValueError("Credenciais do Supabase ausentes nas variáveis de ambiente.")
            self._supabase = create_client(self.url, self.key)
        return self._supabase

    def url_avatar(self, filename: str):
        """URL pública do avatar no bucket, ou None se não houver filename.

        Mesmo formato de Usuario.to_dict(), para o front receber sempre a
        mesma URL por qualquer caminho.
        """
        if not filename:
            return None
        return f"{self.url}/storage/v1/object/public/{self.bucket_name}/{filename}"

    def upload_avatar(self, file_storage) -> str:
        """Valida, otimiza (Pillow) e envia o avatar ao bucket.

        Parâmetros:
            file_storage: FileStorage do Flask com a imagem enviada.

        Retorno:
            Nome do arquivo gerado (ex: e7b44a2c.webp).

        Levanta:
            BionException: 413 se passar de 4MB; 500 se o upload falhar.
            DadosInvalidosError: se o arquivo for vazio, de formato não
                aceito, grande demais em pixels ou não for imagem.
        """
        # Lê no máximo max_size + 1 bytes: o +1 basta para saber que
        # passou do limite sem carregar na memória um corpo gigante.
        file_bytes = file_storage.read(self.max_size + 1)
        if len(file_bytes) > self.max_size:
            raise BionException("O ficheiro excede o limite de 4MB.", 413)
        if not file_bytes:
            raise DadosInvalidosError("O ficheiro enviado está vazio.")

        # 1. Validação e otimização com Pillow (em memória). Qualquer
        # falha aqui é problema do arquivo enviado (422), não do servidor.
        try:
            imagem = Image.open(io.BytesIO(file_bytes))

            # Image.open só lê o cabeçalho: formato e dimensões já
            # existem, mas nada foi decodificado ainda.
            if imagem.format not in FORMATOS_ACEITOS:
                raise DadosInvalidosError("Formato de imagem não aceito. Use JPG, PNG ou WebP.")
            if imagem.width * imagem.height > MAX_PIXELS:
                raise DadosInvalidosError("A imagem tem dimensões grandes demais.")

            # Gira conforme o EXIF (fotos de celular) antes de reduzir.
            imagem = ImageOps.exif_transpose(imagem)

            if imagem.mode != "RGB":
                if imagem.mode in ("RGBA", "LA", "P"):
                    # Transparência vira fundo branco (convert direto
                    # para RGB deixaria preto).
                    imagem = imagem.convert("RGBA")
                    fundo = Image.new("RGB", imagem.size, (255, 255, 255))
                    fundo.paste(imagem, mask=imagem.getchannel("A"))
                    imagem = fundo
                else:
                    imagem = imagem.convert("RGB")

            imagem.thumbnail((256, 256))

            # Re-codifica do zero: o arquivo enviado ao bucket é gerado
            # aqui, então metadados (EXIF) e conteúdo embutido do
            # original não são copiados.
            output_buffer = io.BytesIO()
            imagem.save(output_buffer, format="WEBP", quality=80)
            buffer_bytes = output_buffer.getvalue()
        except BionException:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
            raise DadosInvalidosError("O ficheiro enviado não é uma imagem válida.")

        # 2. Gerar nome único (nunca o nome enviado pelo usuário) e
        # fazer upload para o Supabase. Só aqui um erro é do servidor.
        try:
            novo_nome = f"{uuid.uuid4().hex}.webp"

            self.supabase.storage.from_(self.bucket_name).upload(
                path=novo_nome,
                file=buffer_bytes,
                file_options={"content-type": "image/webp", "x-upsert": "true"}
            )

            return novo_nome
        except Exception:
            # Trata falhas de rede ou limitações do bucket
            logger.exception("Erro no upload do avatar para o Supabase")
            raise BionException("Falha interna ao guardar a imagem no Supabase.", 500)

    def deletar_avatar(self, filename: str) -> None:
        """Remove um avatar do bucket (não faz nada se filename for vazio).

        Falhas só são registradas em log, nunca propagadas: uma imagem
        antiga já apagada não pode bloquear o upload da nova.
        """
        if not filename:
            return

        try:
            self.supabase.storage.from_(self.bucket_name).remove([filename])
        except Exception:
            logger.exception("Erro ao remover o avatar '%s' do Supabase", filename)