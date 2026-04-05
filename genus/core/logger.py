from datetime import datetime


class Logger:
    @staticmethod
    def log(agent, action, data=None):
        timestamp = datetime.utcnow().strftime("%H:%M:%S")

        print(f"[{timestamp}] [{agent}] {action}")

        if data is not None:
            print(f"        ↳ data: {data}")