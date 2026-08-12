"use client";

/**
 * S39 safety takeover — §29.1's `/support/now`.
 *
 * The route exists because §29.1's notification deep links name it ("safety
 * resources→/support/now") and because §22.9's L4 auto-response is delivered
 * whether or not the user is in the chat. It renders the SAME component the
 * L3+ takeover does, so there is one screen and not two that drift.
 *
 * §29.1: it "exits only to Ask Tara or Help — structurally never to paywall,
 * stories or marketing surfaces". Both exits are here and there is no third.
 */

import { SafetyTakeover } from "@/components/ask/SafetyTakeover";
import { useRouter } from "@/i18n/navigation";

export default function SupportNowPage() {
  const router = useRouter();
  return (
    <SafetyTakeover
      onBackToTara={() => router.push("/ask")}
      onGetHelp={() => router.push("/you/help")}
    />
  );
}
