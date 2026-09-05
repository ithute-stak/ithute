export const public_api_url =
    process.env.NEXT_PUBLIC_TUTOR_API_URL?.replace(/\/$/, "") || "/api";

export const removeHttpProtocol = (url: string): string => {
    return url.replace(/^https?:\/\//, "");
};
