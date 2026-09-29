import { SessionView } from "@/components/session-view";

export default async function SessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <SessionView key={sessionId} sessionId={sessionId} />;
}
