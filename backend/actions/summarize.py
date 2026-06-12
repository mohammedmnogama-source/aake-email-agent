import json

from backend.actions.base import ActionHandler
from backend.database.repositories import actions as action_repo


class SummarizeHandler(ActionHandler):
    def execute(
        self,
        email_id: int,
        suggestion_id: int,
        decision_id: int,
        **kwargs,
    ) -> dict:
        action_id = action_repo.create(self.conn, decision_id, email_id, "summarize_only")
        action_repo.update_status(
            self.conn, action_id, "success", result_data=json.dumps({"note": "summarized"})
        )
        self.conn.commit()
        return {"action_id": action_id, "status": "success"}
