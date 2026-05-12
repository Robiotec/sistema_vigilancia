Plan: Fix Camera Editing Conflict Between Name and Unique ID

TL;DR - The issue occurs when editing a camera's name or unique_code, causing the system to create a new camera instead of updating the existing one due to ambiguous identification logic in the backend that falls back to matching by unique_code, potentially updating the wrong camera or creating duplicates.

Steps
1. Modify the POST `/api/cameras` endpoint in `dashboard/back/app/application.py` to remove the unique_code-based update logic (lines ~465-475), ensuring it only updates when an explicit `camera_id` is provided and resolved to an existing camera.
2. Update the PUT `/api/cameras/{camera_id}` endpoint to allow changing the `unique_code` by removing the forced preservation (line ~533: `p["codigo_unico"] = existing.get("unique_code") or p.get("codigo_unico")`).
3. Add database-level validation in the apicentral Camera model to enforce unique_code uniqueness across all companies (modify the constraint in `db/sql/08_apply_approved_saas_model.sql` from per-company to global).
4. Update the frontend form in `dashboard/front/static/web_app.js` to validate unique_code uniqueness before submission (add AJAX check in the form submission handler around line 6796).
5. Test the fix by editing a camera's name and unique_code, ensuring updates occur on the correct camera without creating duplicates.

Relevant files
- `dashboard/back/app/application.py` — Backend camera creation/update endpoints
- `db/sql/08_apply_approved_saas_model.sql` — Database constraints for camera uniqueness
- `dashboard/front/static/web_app.js` — Frontend form validation and submission
- `apicentral/app/models/entities.py` — Camera model definition

Verification
1. Edit an existing camera's name in the dashboard; confirm the existing camera is updated, not a new one created.
2. Attempt to set a duplicate unique_code; confirm the update fails with an error message.
3. Check database for no duplicate cameras after multiple edits.
4. Run API tests for POST/PUT camera endpoints to ensure correct behavior.

Decisions
- Removed unique_code fallback in POST to prevent wrong-camera updates.
- Allowed unique_code changes in PUT to match user expectations.
- Enforced global unique_code uniqueness to prevent conflicts.
- Frontend validation added to catch duplicates before submission.

Further Considerations
1. Consider making camera names unique per company to further reduce confusion.
2. Evaluate if unique_code should be auto-generated and non-editable in the UI.