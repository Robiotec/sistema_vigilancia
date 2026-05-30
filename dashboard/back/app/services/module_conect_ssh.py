import paramiko


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
            
if __name__ == "__main__":
    
    ssh_manager = SSHClientManager(
        host="100.93.62.24",
        user="robiotec",
        password="123456",
        port=22
    )
    try:
        ssh_manager.connect()
        output, error = ssh_manager.execute(
            "cd Documents/VICTOR/Object_Recognition/src/unified/results_presentacion && cat manifest.jsonl"
        )
        print("Output:", output)
        
        
        print("Error:", error)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh_manager.close()
        