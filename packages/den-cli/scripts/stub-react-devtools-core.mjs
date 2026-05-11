// Stub for react-devtools-core -- only used by ink when DEV_TOOLS env is set.
// In production CLI builds we never enable devtools, so a no-op default export
// keeps the static ESM import resolvable without pulling in the real package
// (which has peer-dep conflicts and adds ~1MB).
const noop = () => {};
export default { connectToDevTools: noop };
export const connectToDevTools = noop;
