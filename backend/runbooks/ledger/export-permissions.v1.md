# Export permissions

Creating an export requires exports.create for the requesting member.

Downloading an artifact requires exports.download.

A permission_denied event with HTTP 403 identifies a rejected request.

Compare the requesting member ID with current permissions; do not infer another member's access.

Ask the account administrator to review the intended role before granting access.

A permissions_updated event is configuration history, not proof of a failed request.
