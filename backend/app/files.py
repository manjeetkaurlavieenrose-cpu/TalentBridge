import hashlib, os, re, uuid, zipfile, io

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
MAX_UNCOMPRESSED = 30 * 1024 * 1024


class FileRejected(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def sniff(data, filename):
    """Decide the type from content, never from the client-supplied name or MIME."""
    if not data:
        raise FileRejected("empty_file", "The file is empty.")
    ext = os.path.splitext(filename or "")[1].lower()
    if data.startswith(PDF_MAGIC):
        if ext != ".pdf": raise FileRejected("extension_mismatch", "File extension does not match its content.")
        return "pdf", "application/pdf"
    if data.startswith(ZIP_MAGIC):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = z.namelist()
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise FileRejected("unsupported_type", "Only PDF and DOCX files are accepted.")
            if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED:
                raise FileRejected("too_large_expanded", "The document expands to an unsafe size.")
        except zipfile.BadZipFile:
            raise FileRejected("corrupt_file", "The file is corrupt.")
        if ext != ".docx": raise FileRejected("extension_mismatch", "File extension does not match its content.")
        return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raise FileRejected("unsupported_type", "Only PDF and DOCX files are accepted.")


def safe_name(name):
    name = os.path.basename(name or "cv")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:120] or "cv"


class LocalStorage:
    """Files live outside any web root under random keys. Swap for S3/Supabase by keeping this interface."""
    def __init__(self, root):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key):
        p = os.path.abspath(os.path.join(self.root, key))
        if not p.startswith(self.root + os.sep):
            raise ValueError("bad key")
        return p

    def put(self, data, ext):
        key = f"{uuid.uuid4().hex}.{ext}"
        with open(self._path(key), "wb") as f:
            f.write(data)
        return key, hashlib.sha256(data).hexdigest()

    def get(self, key):
        with open(self._path(key), "rb") as f:
            return f.read()

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


class S3Storage:
    """Same interface as LocalStorage, for any S3-compatible bucket. Needs `pip install boto3` and normal AWS credentials
    (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION), or S3_ENDPOINT for Supabase / R2 / MinIO. Keep the bucket private."""
    def __init__(self, bucket, prefix="cv/", endpoint=None, client=None):
        if client is None:
            import boto3
            client = boto3.client("s3", endpoint_url=endpoint or None)
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def _k(self, key):
        if "/" in key or ".." in key:
            raise ValueError("bad key")
        return self.prefix + key

    def put(self, data, ext):
        key = f"{uuid.uuid4().hex}.{ext}"
        self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data, ServerSideEncryption="AES256")
        return key, hashlib.sha256(data).hexdigest()

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))


def make_storage(cfg):
    if cfg.storage_backend == "s3":
        if not cfg.s3_bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 needs S3_BUCKET.")
        return S3Storage(cfg.s3_bucket, cfg.s3_prefix, cfg.s3_endpoint)
    return LocalStorage(cfg.upload_dir)
