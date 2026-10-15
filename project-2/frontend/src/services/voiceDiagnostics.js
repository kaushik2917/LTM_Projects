// Ephemeral operator display only. Raw speech is never logged or persisted here.
export function maskVoiceText(text=''){
 return text.replace(/\b(?:my\s+)?(?:pin|otp|cvv|password|passcode)\s*(?:is|:|=)?\s+[^;\n]+/gi,'[CREDENTIAL REDACTED]')
  .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,'[EMAIL REDACTED]')
  .replace(/(?<!\w)\+?\d(?:[ -]?\d){5,18}(?!\w)/g,'[NUMBER REDACTED]');
}
export const initialVoiceDiagnostics={microphonePermission:'UNKNOWN',audioStreamActive:false,recognitionActive:false,speechDetected:false,interimTranscript:'',finalTranscript:'',lastRecognitionError:null,provider:'browser-web-speech'};
