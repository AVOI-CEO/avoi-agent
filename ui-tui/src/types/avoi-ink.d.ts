// AVOI Ink
declare module '@avoi/ink' {
  // ---- re-exports from ink ----
  export { default as render } from 'ink';
  export { default as Box } from 'ink/build/components/Box.js';
  export { default as Text } from 'ink/build/components/Text.js';
  export { default as Static } from 'ink/build/components/Static.js';
  export { default as Transform } from 'ink/build/components/Transform.js';
  export { default as Newline } from 'ink/build/components/Newline.js';
  export { default as Spacer } from 'ink/build/components/Spacer.js';
  export { default as Link } from 'ink/build/components/Link.js';
  export { default as AppContext } from 'ink/build/components/AppContext.js';
  export { default as StdinContext } from 'ink/build/components/StdinContext.js';
  export { default as StdoutContext } from 'ink/build/components/StdoutContext.js';
  export { default as StderrContext } from 'ink/build/components/StderrContext.js';
  export { default as Color } from 'ink/build/components/Color.js';
  export { default as measureElement } from 'ink/build/measure-element.js';
  export { useStdin } from 'ink';
  export { useStdout } from 'ink';
  export { useStderr } from 'ink';
  export { useInput } from 'ink';
  export { useApp } from 'ink';
  export { default as Static } from 'ink';
  export { default as Color } from 'ink';
  export { render } from 'ink';
  export { default as _jsx } from 'ink';

  // ---- upstream additions (ScrollBox, NoSelect etc) ----
  export { default as ScrollBox, type ScrollBoxHandle } from '@avoi/ink/build/components/ScrollBox.js';
  export { default as NoSelect } from '@avoi/ink/build/components/NoSelect.js';
  export { default as AlternateScreen } from '@avoi/ink/build/components/AlternateScreen.js';
  export { useSelection } from '@avoi/ink';
  export { useHasSelection } from '@avoi/ink';
  export { useTerminalTitle } from '@avoi/ink';
  export { withInkSuspended, type RunExternalProcess } from '@avoi/ink';
  export type { InputEvent, Key } from '@avoi/ink';
}