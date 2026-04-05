import json
import os


class Memory:
    FILE = "memory.json"

    @classmethod
    def load(cls):
        if not os.path.exists(cls.FILE):
            return []

        with open(cls.FILE, "r") as f:
            return json.load(f)

    @classmethod
    def save(cls, data):
        with open(cls.FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def add_feedback(cls, feedback):
        data = cls.load()
        data.append(feedback)
        cls.save(data)

    @classmethod
    def get_stats(cls):
        data = cls.load()

        # 🔥 nur die letzten 10 Einträge berücksichtigen
        recent = data[-10:]

        total = len(recent)

        if total == 0:
            return {"total": 0, "good_ratio": 0}

        good = recent.count("GOOD")

        return {
            "total": total,
            "good_ratio": good / total
        }