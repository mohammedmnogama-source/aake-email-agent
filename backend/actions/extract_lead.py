import json

from backend.actions.base import ActionHandler
from backend.database.repositories import actions as action_repo
from backend.database.repositories import leads as lead_repo


class ExtractLeadHandler(ActionHandler):
    def execute(
        self,
        email_id: int,
        suggestion_id: int,
        decision_id: int,
        extracted_data: dict | None = None,
        **kwargs,
    ) -> dict:
        action_id = action_repo.create(self.conn, decision_id, email_id, "extract_lead_info")
        self.conn.commit()

        try:
            lead_id = lead_repo.create(
                self.conn,
                email_id=email_id,
                action_id=action_id,
                extracted=extracted_data or {},
                raw_extracted=json.dumps(extracted_data) if extracted_data else None,
            )
            result = {"lead_id": lead_id}
            action_repo.update_status(
                self.conn, action_id, "success", result_data=json.dumps(result)
            )
            self.conn.commit()
            return {"action_id": action_id, "status": "success", "lead_id": lead_id}

        except Exception as e:
            action_repo.update_status(
                self.conn, action_id, "failed", error_message=str(e)
            )
            self.conn.commit()
            raise
