"use client";

/**
 * S14's listen-to-your-brief control (§27, §24.3's `AudioPlayer`).
 *
 * `AudioPlayer` has described itself as "the morning-brief player on S14"
 * since M7 and S14 never rendered one — `daily_briefings.audio_ref` was stored
 * and read back by nobody. This is the missing half.
 *
 * §27 makes briefs LISTEN-ONLY: no download, no speed ramp, and the written
 * brief below stays the peer of the audio rather than a fallback for it. The
 * component asks for nothing until the user presses play, because a brief is
 * twenty to thirty seconds of synthesis and pre-fetching it would spend a
 * vendor call on every morning nobody listened to.
 */

import { useEffect, useRef, useState } from "react";

import { AudioPlayer } from "@/components/ui";
import { apiUrl } from "@/lib/api";

type Phase = "idle" | "loading" | "ready" | "unavailable";

export function BriefAudio({ localDate }: { localDate: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  async function load() {
    setPhase("loading");
    try {
      const response = await fetch(apiUrl(`/v1/today/audio?date=${localDate}`), {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        // §30.1: a missing voice is a designed state. The written brief is
        // right there and unaffected, so this says so instead of erroring.
        setPhase("unavailable");
        return;
      }
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = URL.createObjectURL(await response.blob());

      const audio = audioRef.current ?? new Audio();
      audioRef.current = audio;
      audio.src = urlRef.current;
      audio.onended = () => setPlaying(false);
      setPhase("ready");
      setPlaying(true);
      await audio.play().catch(() => setPlaying(false));
    } catch {
      setPhase("unavailable");
    }
  }

  function toggle() {
    const audio = audioRef.current;
    if (playing && audio) {
      audio.pause();
      setPlaying(false);
      return;
    }
    if (phase === "ready" && audio) {
      setPlaying(true);
      void audio.play().catch(() => setPlaying(false));
      return;
    }
    void load();
  }

  return (
    <div data-testid="brief-audio">
      <AudioPlayer
        playing={playing}
        onTogglePlay={toggle}
        progress={0}
        elapsed="0:00"
        duration="0:00"
        unavailable={phase === "unavailable"}
      />
    </div>
  );
}
