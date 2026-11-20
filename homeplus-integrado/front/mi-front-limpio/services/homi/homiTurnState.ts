export type HomiTurnStateValue =
  | 'idle'
  | 'sending'
  | 'success'
  | 'error'
  | 'WAITING_CONFIRMATION'
  | 'EXECUTING'
  | 'PARTIAL'
  | 'CANCELLED';

export type HomiTurnState =
  | HomiTurnStateValue
  | { status: HomiTurnStateValue }
  | { state: HomiTurnStateValue }
  | { value: HomiTurnStateValue }
  | { turnState: HomiTurnStateValue }
  | Record<string, unknown>;

export type HomiTurnEvent =
  | { type: 'SUBMIT'; text?: string; empty?: boolean }
  | { type: 'RESOLVED' }
  | { type: 'REJECTED' }
  | { type: 'DISMISS_ERROR' }
  | { type: 'ABORT' }
  | { type: 'CANCEL' };

const isEmptySubmit = (event: HomiTurnEvent): boolean => {
  if (event.type !== 'SUBMIT') return false;
  if (event.empty === true) return true;
  if (typeof event.text === 'string') return event.text.trim() === '';
  return false;
};

const STATE_KEYS = ['status', 'state', 'value', 'turnState'] as const;

const getStateKey = (state: HomiTurnState): (typeof STATE_KEYS)[number] | null => {
  if (typeof state === 'string') return null;
  for (const key of STATE_KEYS) {
    if (Object.prototype.hasOwnProperty.call(state, key)) return key;
  }
  return 'status';
};

const unwrap = (state: HomiTurnState): HomiTurnStateValue => {
  if (typeof state === 'string') return state;
  const key = getStateKey(state);
  return key ? (state as Record<string, unknown>)[key] as HomiTurnStateValue : 'idle';
};

const wrap = (state: HomiTurnState, value: HomiTurnStateValue): HomiTurnState => {
  if (typeof state === 'string') return value;
  const key = getStateKey(state) ?? 'status';
  return { ...state, [key]: value };
};

export const homiTurnReducer = (
  stateOrEvent: HomiTurnState | HomiTurnEvent,
  eventMaybe?: HomiTurnEvent,
): HomiTurnState => {
  let state: HomiTurnState;
  let event: HomiTurnEvent;
  if (eventMaybe === undefined && typeof stateOrEvent === 'object' && stateOrEvent !== null && 'type' in (stateOrEvent as object)) {
    state = 'idle';
    event = stateOrEvent as HomiTurnEvent;
  } else {
    state = stateOrEvent as HomiTurnState;
    event = eventMaybe as HomiTurnEvent;
  }
  const current = unwrap(state);

  if (event.type === 'SUBMIT') {
    if (isEmptySubmit(event)) return state;
    if (current === 'sending') return state;
    return wrap(state, 'sending');
  }

  if (event.type === 'RESOLVED') {
    if (current !== 'sending') return state;
    return wrap(state, 'success');
  }

  if (event.type === 'REJECTED') {
    if (current !== 'sending') return state;
    return wrap(state, 'error');
  }

  if (event.type === 'DISMISS_ERROR') {
    if (current !== 'error') return state;
    return wrap(state, 'idle');
  }

  if (event.type === 'ABORT' || event.type === 'CANCEL') {
    return wrap(state, 'idle');
  }

  return state;
};

export const reduceHomiTurn = homiTurnReducer;
export const homiTurnStateReducer = homiTurnReducer;
export const homiReducer = homiTurnReducer;

export const initialHomiTurnState: HomiTurnState = 'idle';
export const HOMI_TURN_INITIAL_STATE = 'idle';

export default homiTurnReducer;
