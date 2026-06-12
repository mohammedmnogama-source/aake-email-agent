import sqlite3
from abc import ABC, abstractmethod


class ActionHandler(ABC):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @abstractmethod
    def execute(self, email_id: int, suggestion_id: int, decision_id: int, **kwargs) -> dict:
        """Execute the action. Returns result dict stored in actions_taken.result_data."""
