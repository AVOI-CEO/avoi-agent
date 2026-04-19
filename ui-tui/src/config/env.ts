export const STARTUP_RESUME_ID = (process.env.avoi_TUI_RESUME ?? '').trim()
export const MOUSE_TRACKING = !/^(?:1|true|yes|on)$/i.test((process.env.avoi_TUI_DISABLE_MOUSE ?? '').trim())
