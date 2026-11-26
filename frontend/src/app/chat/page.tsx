import ChatBox from "@/components/ChatBox";

export default function ChatPage() {
  return (
    <>
      <div className="page-intro">
        <p className="eyebrow">ACCOMPAGNEMENT · IIT &amp; ISB</p>
        <h1>Parlons de votre projet d&apos;études.</h1>
        <p>Posez vos questions sur les formations et avancez à votre rythme.</p>
      </div>
      <ChatBox />
    </>
  );
}
