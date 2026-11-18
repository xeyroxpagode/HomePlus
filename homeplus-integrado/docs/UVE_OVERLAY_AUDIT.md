# UVE natural overlay dismiss audit

## KEEP

- `ActionSheet` and its inline pickers: dedicated backdrop target, inner panel
  isolation, keyboard-first dismiss, Android back, close-disabled guard.
- `AccountSheet`, `QuickActionSheet`, `HouseholdSwitcherSheet`: backdrop dismiss,
  inner responder isolation, close affordance; existing swipe stays unchanged.
- `PlannerSheetHost`: explicit backdrop reason, inner event isolation, submit lock,
  Android back and draft-close contract.
- `InviteLinkSheetFinal` and Planner link-task modal: dedicated backdrop and inner
  surface isolation.

## ADOPT BACKDROP DISMISS

- Messages new-conversation chooser: temporary selection, no draft.
- Messages task picker: temporary selection, no draft.
- Family action feedback and snackbar: outside tap dismisses; the visual card no
  longer propagates that tap to the backdrop.

## DO NOT APPLY

- Message media preview: contains an unsent attachment draft.
- Message audio recorder: active capture/cancel lifecycle.
- Message-to-task action: editable title and possible validation error.
- Profile, Inventory, Calendar and Feed editors: closing may discard form data.
- Family SOS: critical confirmation requires an explicit decision.
- destructive confirmation surfaces and any operation with `closeDisabled`:
  preserve the current intentional contract.
- fullscreen image viewer: not a sheet/backdrop composition; explicit Close and
  Android back remain authoritative.

