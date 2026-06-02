// When a conversation is opened (sidebar click, /c/<id> permalink, back/forward),
// the mode picker must reflect THAT conversation's mode — not whatever mode was
// last globally selected. ``activeMode`` is a single persisted global value, so
// without this reconciliation a continued turn is sent with a stale mode (e.g.
// a tutor conversation sending 'facilitate' because the picker drifted).
//
// Returns the conversation's mode when it is a recognised mode id, otherwise
// leaves the current selection untouched.
export function pickOpenedMode(
  convMode: string | null | undefined,
  knownModes: readonly string[] | readonly { id: string }[],
  current: string,
): string {
  if (!convMode) return current;
  const ids = knownModes.map((m) => (typeof m === "string" ? m : m.id));
  return ids.includes(convMode) ? convMode : current;
}
