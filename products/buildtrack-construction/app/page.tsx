import { chatGPTSignInPath, getChatGPTUser } from "./chatgpt-auth";
import { OperationsWorkspace } from "./operations-workspace";

export const dynamic = "force-dynamic";

export default async function Home() {
  const user = await getChatGPTUser();

  return (
    <OperationsWorkspace
      signInPath={chatGPTSignInPath("/")}
      user={user ? { displayName: user.displayName, email: user.email } : null}
    />
  );
}
