# LinkedIn API Later

Live posting is not part of v0.

Before any LinkedIn API adapter can post:
- `linkedin_api_enabled` must be true.
- OAuth credentials must exist.
- The draft must have a valid approval record.
- Draft version and content hash must match the approval.
- Media must have separate approval if attached.
- Cost Guard must allow LinkedIn API calls.
- Target must remain the personal LinkedIn profile.

Until then, use assisted manual posting packages only.
