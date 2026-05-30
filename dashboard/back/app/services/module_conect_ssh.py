from __future__ import annotations

import shlex

import paramiko

DEFAULT_REMOTE_HOST = "100.93.62.24"
DEFAULT_REMOTE_USER = "robiotec"
DEFAULT_REMOTE_PASSWORD = "123456"
DEFAULT_REMOTE_PORT = 22
DEFAULT_REMOTE_MANIFEST_PATH = (
    "/home/robiotec/Documents/VICTOR/Object_Recognition/src/unified/results_presentacion/manifest.jsonl"
)


class SSHClientManager:
    def __init__(self, host, user, password=None, port=22, key_path=None):
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.key_path = key_path
        self.client = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if self.key_path:
            key = paramiko.RSAKey.from_private_key_file(self.key_path)
            self.client.connect(
                hostname=self.host,
                username=self.user,
                port=self.port,
                pkey=key
            )
        else:
            self.client.connect(
                hostname=self.host,
                username=self.user,
                password=self.password,
                port=self.port
            )

        print(f"[OK] Conectado a {self.host}")

    def execute(self, command):
        if not self.client:
            raise Exception("No hay conexión SSH activa")

        stdin, stdout, stderr = self.client.exec_command(command)

        output = stdout.read().decode()
        error = stderr.read().decode()

        return output, error

    def close(self):
        if self.client:
            self.client.close()
            print("[OK] Conexión cerrada")


def fetch_remote_manifest_text(
    *,
    host: str = DEFAULT_REMOTE_HOST,
    user: str = DEFAULT_REMOTE_USER,
    password: str | None = DEFAULT_REMOTE_PASSWORD,
    port: int = DEFAULT_REMOTE_PORT,
    key_path: str | None = None,
    manifest_path: str = DEFAULT_REMOTE_MANIFEST_PATH,
) -> str:
    ssh_manager = SSHClientManager(
        host=host,
        user=user,
        password=password,
        port=port,
        key_path=key_path,
    )
    try:
        ssh_manager.connect()
        output, error = ssh_manager.execute(f"cat {shlex.quote(manifest_path)}")
        output = output.strip()
        error = error.strip()
        if error:
            raise RuntimeError(error)
        return output
    finally:
        ssh_manager.close()


def fetch_remote_manifest_lines(**kwargs) -> list[str]:
    output = fetch_remote_manifest_text(**kwargs)
    return [line for line in output.splitlines() if line.strip()]


if __name__ == "__main__":
    try:
        output = fetch_remote_manifest_text()
        print("Output:", output)
    except Exception as e:
        print(f"Error: {e}")
