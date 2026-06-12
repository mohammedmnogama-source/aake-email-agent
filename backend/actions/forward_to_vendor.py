import json
import os
from datetime import datetime, timezone

from backend.actions.base import ActionHandler
from backend.database.repositories import actions as action_repo
from backend.email.draft_saver import save_draft


class ForwardToVendorHandler(ActionHandler):
    def execute(
        self,
        email_id: int,
        suggestion_id: int,
        decision_id: int,
        to: str,
        subject: str,
        content: str,
        **kwargs,
    ) -> dict:
        action_id = action_repo.create(self.conn, decision_id, email_id, "forward_to_vendor")
        self.conn.commit()

        test_mode_row = self.conn.execute(
            "SELECT value FROM settings WHERE key = 'test_mode'"
        ).fetchone()
        test_mode = test_mode_row and test_mode_row["value"] == "1"

        try:
            if test_mode:
                os.makedirs("data/test_drafts", exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                path = f"data/test_drafts/{ts}_{email_id}_fwd.txt"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"To: {to}\nSubject: {subject}\n\n{content}")
                result = {"test_file": path}
                status = "success"  # test mode
            else:
                uid = save_draft(to=to, subject=subject, body=content)
                result = {"draft_uid": uid}
                status = "success"

            action_repo.update_status(
                self.conn, action_id, status, result_data=json.dumps(result)
            )
            self.conn.commit()
            return {"action_id": action_id, "status": status, **result}

        except Exception as e:
            action_repo.update_status(
                self.conn, action_id, "failed", error_message=str(e)
            )
            self.conn.commit()
            raise
