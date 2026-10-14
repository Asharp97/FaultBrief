# Export job investigation

Correlate an export job and request logs by request_id.

STORAGE_WRITE_FAILED with an export_failed event reporting a rejected artifact write supports a storage-write failure; it does not establish the underlying infrastructure cause.

EXPORT_TIMEOUT identifies a timeout symptom.

If downstream logs are unavailable or coverage is partial, report an inconclusive root cause and request downstream traces.

A completed job and matching export_completed event establish that the observed export completed, not that every user issue is resolved.
