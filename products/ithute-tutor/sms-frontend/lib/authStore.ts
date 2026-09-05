let accessToken: string | null = null;

export const authStore = {
    getToken: () => accessToken,
    setToken: (token: string | null) => {
        accessToken = token;
    },
};