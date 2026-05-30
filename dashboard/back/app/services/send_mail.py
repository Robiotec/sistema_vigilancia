import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Cuenta Outlook
correo_emisor = "robiotec@grupominerobonanza.com"
password = "Bonanz@2024"

# Lista de destinatarios
destinatarios = [
    "yuchuari@grupominerobonanza.com",
    "pclemente@grupominerobonanza.com",
    "dguevara@grupominerobonanza.com"
]

asunto = "Correo Informativo - Prueba de Envío"

mensaje = """
Estimados,
Este es un correo de prueba enviado automáticamente mediante Python.

Saludos cordiales.
"""

try:
    # Servidor SMTP de Outlook
    servidor = smtplib.SMTP("smtp.office365.com", 587)
    servidor.starttls()
    servidor.login(correo_emisor, password)

    for destinatario in destinatarios:
        msg = MIMEMultipart()
        msg["From"] = correo_emisor
        msg["To"] = destinatario
        msg["Subject"] = asunto

        msg.attach(MIMEText(mensaje, "plain"))

        servidor.sendmail(
            correo_emisor,
            destinatario,
            msg.as_string()
        )

        print(f"✓ Enviado a {destinatario}")

    servidor.quit()
    print("\nProceso completado.")

except Exception as e:
    print(f"Error: {e}")