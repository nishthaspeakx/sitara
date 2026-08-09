/**
 * The §24.3 component library — 49 components, and exactly 49.
 *
 *   9 foundation + 18 Sitara-specific + 10 structure + 12 feedback
 *
 * §34.7 fixed the count at 48; CC-007 added KundliChart and made it 49. The
 * diagram itself lands in M10 — the component ships its contract and an honest
 * unbuilt state now, so this count is true rather than aspirational.
 *
 * "No screen may ship a one-off component without design-system review" (§24.3).
 * `library.test.ts` asserts the counts against this file, so adding a component
 * without amending the manifest fails CI rather than passing quietly.
 */

// ── Foundation (9) ──────────────────────────────────────────────────────────
export { Button, type ButtonProps, type ButtonVariant } from "./Button";
export { IconButton, type IconButtonProps, type IconButtonVariant } from "./IconButton";
export { Chip, type ChipProps, type ChipVariant } from "./Chip";
export { Input, type InputProps, type InputKind } from "./Input";
export { SearchField, type SearchFieldProps } from "./SearchField";
export { Select, type SelectProps, type SelectOption } from "./Select";
export { Toggle, type ToggleProps } from "./Toggle";
export { Slider, type SliderProps } from "./Slider";
export { SegmentedControl, type SegmentedControlProps, type Segment } from "./SegmentedControl";

// ── Sitara-specific (17) ────────────────────────────────────────────────────
export { TaraPresence, type TaraPresenceProps } from "./TaraPresence";
export { VoiceBar, type VoiceBarProps, type VoiceState, VOICE_STATES } from "./VoiceBar";
export { BriefCard, type BriefCardProps } from "./BriefCard";
export { TrustSheet, type TrustSheetProps } from "./TrustSheet";
export { ConfidenceChip, type ConfidenceChipProps } from "./ConfidenceChip";
export {
  KundliChart,
  type KundliChartProps,
  type KundliHouse,
  type KundliStyle,
  type Graha,
  KUNDLI_STYLES,
  GRAHAS,
} from "./KundliChart";
export { MemoryChip, type MemoryChipProps, type MemoryChipState } from "./MemoryChip";
export { MemoryCard, type MemoryCardProps, type MemoryType, MEMORY_TYPES } from "./MemoryCard";
export { PanchangStrip, type PanchangStripProps, type PanchangEntry } from "./PanchangStrip";
export { TimingBar, type TimingBarProps, type TimingBand, type TimingQuality } from "./TimingBar";
export { FamilyCard, type FamilyCardProps } from "./FamilyCard";
export { ChatBubble, type ChatBubbleProps, type ChatAuthor, type CitedSpan } from "./ChatBubble";
export { ReflectionPrompt, type ReflectionPromptProps } from "./ReflectionPrompt";
export { FestivalBanner, type FestivalBannerProps } from "./FestivalBanner";
export { StoryRing, type StoryRingProps, type StoryRingState } from "./StoryRing";
export { CallControls, type CallControlsProps } from "./CallControls";
export {
  VoiceNoteBubble,
  type VoiceNoteBubbleProps,
  type VoiceNoteMode,
  type TranscriptStatus,
  PLAYBACK_SPEEDS,
} from "./VoiceNoteBubble";
export { VerifiedSourceRow, type VerifiedSourceRowProps, type SourceState } from "./VerifiedSourceRow";

// ── Structure (10) ──────────────────────────────────────────────────────────
export { TabBar, type TabBarProps, type TabId, TABS } from "./TabBar";
export { Header, type HeaderProps, type HeaderVariant } from "./Header";
export { Sheet, type SheetProps } from "./Sheet";
export { Modal, type ModalProps } from "./Modal";
export { Card, type CardProps, type CardTone } from "./Card";
export { ListRow, type ListRowProps } from "./ListRow";
export { SectionHeader, type SectionHeaderProps } from "./SectionHeader";
export { Divider, type DividerProps } from "./Divider";
export { ProgressDots, type ProgressDotsProps, ONBOARDING_STEPS } from "./ProgressDots";
export { Stepper, type StepperProps, type Step } from "./Stepper";

// ── Feedback (12) ───────────────────────────────────────────────────────────
export { Skeleton, type SkeletonProps, type SkeletonVariant } from "./Skeleton";
export { EmptyState, type EmptyStateProps, type EmptyStateId, EMPTY_STATES } from "./EmptyState";
export { ErrorState, type ErrorStateProps, type ErrorEnvelope } from "./ErrorState";
export { OfflineBanner, type OfflineBannerProps } from "./OfflineBanner";
export { Toast, type ToastProps, type ToastTone } from "./Toast";
export { PaywallPanel, type PaywallPanelProps } from "./PaywallPanel";
export { PriceCard, type PriceCardProps } from "./PriceCard";
export { ReceiptRow, type ReceiptRowProps, type ReceiptStatus } from "./ReceiptRow";
export { ConsentRow, type ConsentRowProps } from "./ConsentRow";
export {
  NotificationPrefRow,
  type NotificationPrefRowProps,
  type NotificationChannel,
  type ChannelState,
  NOTIFICATION_CHANNELS,
} from "./NotificationPrefRow";
export { AudioPlayer, type AudioPlayerProps } from "./AudioPlayer";
export { RatingTap, type RatingTapProps, type RatingChoice } from "./RatingTap";

// ── Shared primitives (not components) ──────────────────────────────────────
export {
  cn,
  focusRing,
  touchTarget,
  controlHeight,
  motionStandard,
  ICON_STROKE,
  TARA_SIZES,
  TARA_STATES,
  CONFIDENCE_STATES,
  type MessageKey,
  type TaraSize,
  type TaraState,
  type ConfidenceState,
} from "./_util";
export { TARA_ASSETS, TARA_ASSET_STATUS, type TaraAsset } from "./tara-assets";

/**
 * The manifest the §24.3 count is asserted against. Families are the spec's own
 * four; the names are the spec's own names (TrustSheet, not WhyThisSheet — §34.7).
 */
export const LIBRARY = {
  foundation: [
    "Button",
    "IconButton",
    "Chip",
    "Input",
    "SearchField",
    "Select",
    "Toggle",
    "Slider",
    "SegmentedControl",
  ],
  sitara: [
    "TaraPresence",
    "VoiceBar",
    "BriefCard",
    "TrustSheet",
    "ConfidenceChip",
    "KundliChart",
    "MemoryChip",
    "MemoryCard",
    "PanchangStrip",
    "TimingBar",
    "FamilyCard",
    "ChatBubble",
    "ReflectionPrompt",
    "FestivalBanner",
    "StoryRing",
    "CallControls",
    "VoiceNoteBubble",
    "VerifiedSourceRow",
  ],
  structure: [
    "TabBar",
    "Header",
    "Sheet",
    "Modal",
    "Card",
    "ListRow",
    "SectionHeader",
    "Divider",
    "ProgressDots",
    "Stepper",
  ],
  feedback: [
    "Skeleton",
    "EmptyState",
    "ErrorState",
    "OfflineBanner",
    "Toast",
    "PaywallPanel",
    "PriceCard",
    "ReceiptRow",
    "ConsentRow",
    "NotificationPrefRow",
    "AudioPlayer",
    "RatingTap",
  ],
} as const;

/** §34.7 set this at 48; CC-007 added KundliChart. */
export const LIBRARY_SIZE = 49;
