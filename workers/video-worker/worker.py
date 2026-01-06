import os
import time
import pika
import signal
import sys

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
QUEUE_NAME = os.getenv("VIDEO_QUEUE_NAME", "video_jobs")


def connect_rabbitmq(url: str, max_attempts: int = 60):
    """
    Надёжное подключение к RabbitMQ с повторными попытками.
    RabbitMQ (особенно management) может стартовать 40-60 секунд.
    """
    params = pika.URLParameters(url)

    # важные параметры, чтобы не висеть вечно и не падать слишком быстро
    params.heartbeat = 60
    params.blocked_connection_timeout = 60
    params.socket_timeout = 10
    params.connection_attempts = 1  # мы сами делаем retry
    params.retry_delay = 0

    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"🐇 Connecting to RabbitMQ (attempt {attempt}/{max_attempts})...")
            conn = pika.BlockingConnection(params)
            print("✅ RabbitMQ connected")
            return conn
        except Exception as e:
            last_err = e
            sleep_s = min(2 + attempt, 10)
            print(f"❌ RabbitMQ not ready: {e}. Sleep {sleep_s}s")
            time.sleep(sleep_s)

    raise RuntimeError(f"RabbitMQ connection failed after retries: {last_err}")


class VideoWorker:
    def __init__(self):
        self.running = True
        self.connection = None
        self.channel = None

    def stop(self, signum=None, frame=None):
        print("🛑 Stopping video worker...")

        self.running = False
        try:
            if self.channel and self.channel.is_open:
                self.channel.stop_consuming()
        except Exception:
            pass

        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
        except Exception:
            pass

        sys.exit(0)

    def on_message(self, ch, method, properties, body):
        try:
            print("📩 Received job:")
            print(body.decode(errors="ignore"))

            # имитация работы
            time.sleep(3)

            ch.basic_ack(delivery_tag=method.delivery_tag)
            print("✅ Job processed")
        except Exception as e:
            # если обработка упала — лучше "вернуть" задачу в очередь
            print(f"❌ Job failed: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        print("🚀 Video worker started")
        print(f"🔧 RABBITMQ_URL={RABBITMQ_URL}")
        print(f"🔧 QUEUE_NAME={QUEUE_NAME}")

        self.connection = connect_rabbitmq(RABBITMQ_URL, max_attempts=60)
        self.channel = self.connection.channel()

        # Prefetch 1 — чтобы worker не брал пачку задач сразу
        self.channel.basic_qos(prefetch_count=1)

        self.channel.queue_declare(queue=QUEUE_NAME, durable=True)

        self.channel.basic_consume(
            queue=QUEUE_NAME,
            on_message_callback=self.on_message,
            auto_ack=False
        )

        print(f"👂 Waiting for messages in queue '{QUEUE_NAME}'...")
        self.channel.start_consuming()


if __name__ == "__main__":
    VideoWorker().run()
