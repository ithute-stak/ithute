# Implementation note

The transfer endpoint performs the tenant ownership change and associated mail-resource tenant updates in one database transaction. If any part fails, the transaction does not commit.
