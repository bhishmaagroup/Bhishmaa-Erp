from flask_mail import Message
from extensions import mail
import threading
from flask import current_app


def async_send(app, msg):

    with app.app_context():

        try:

            mail.send(msg)

            print("✅ EMAIL SENT SUCCESSFULLY")

        except Exception as e:

            print("❌ EMAIL ERROR:")
            print(str(e))


def send_system_email(
    to_email,
    subject,
    body,
    is_html=False
):

    try:

        msg = Message(

            subject=subject,

            recipients=[to_email],

            sender=current_app.config[
                "MAIL_DEFAULT_SENDER"
            ]
        )

        if is_html:

            msg.html = body

        else:

            msg.body = body

        thread = threading.Thread(

            target=async_send,

            args=(
                current_app._get_current_object(),
                msg
            )
        )

        thread.start()

        return True

    except Exception as e:

        print("❌ SEND SYSTEM EMAIL ERROR:")
        print(str(e))

        return False
