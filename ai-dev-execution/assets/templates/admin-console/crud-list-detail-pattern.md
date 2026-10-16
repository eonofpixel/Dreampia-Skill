# Admin CRUD/List/Detail Pattern

visibility: internal_only

## Standard Pages

- `/admin/dashboard`
- `/admin/{resource}` list
- `/admin/{resource}/new`
- `/admin/{resource}/:id` detail
- `/admin/{resource}/:id/edit`
- `/admin/settings`

## List Requirements

- search, filter, sort, pagination
- empty/loading/error states
- export permission check
- row-level action permission

## Detail Requirements

- immutable id/version
- status history
- audit log link
- safe destructive actions separated
