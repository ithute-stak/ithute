function base64urlToBuffer(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

function bufferToBase64url(value: ArrayBuffer | null): string | null {
  if (!value) return null;
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function registrationOptionsFromJSON(value: Record<string, any>): PublicKeyCredentialCreationOptions {
  return {
    ...value,
    challenge: base64urlToBuffer(String(value.challenge || "")),
    user: {
      ...value.user,
      id: base64urlToBuffer(String(value.user?.id || "")),
    },
    excludeCredentials: Array.isArray(value.excludeCredentials)
      ? value.excludeCredentials.map((item: any) => ({
          ...item,
          id: base64urlToBuffer(String(item.id || "")),
        }))
      : undefined,
  } as PublicKeyCredentialCreationOptions;
}

export function authenticationOptionsFromJSON(value: Record<string, any>): PublicKeyCredentialRequestOptions {
  return {
    ...value,
    challenge: base64urlToBuffer(String(value.challenge || "")),
    allowCredentials: Array.isArray(value.allowCredentials)
      ? value.allowCredentials.map((item: any) => ({
          ...item,
          id: base64urlToBuffer(String(item.id || "")),
        }))
      : undefined,
  } as PublicKeyCredentialRequestOptions;
}

export function registrationCredentialToJSON(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : [],
    },
  };
}

export function authenticationCredentialToJSON(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: bufferToBase64url(response.userHandle),
    },
  };
}
