import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  FlatList,
  StyleSheet,
  View,
  type ListRenderItemInfo,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';

import { AppText } from '../ui/AppText';
import { HomePlusIcon } from '../../constants/icons';
import type { HomiMessage, HomiTaskDto } from '../../services/homi/homiMessages';
import type { HomiTheme } from './homiVisual';
import {
  homiEasing,
  homiFormatClock,
  homiFormatFileSize,
  homiMotion,
  homiSpacing,
  useHomiTheme,
  useReducedMotion,
} from './homiVisual';
import { HomiPressable } from './HomiPressable';
import { HomiTaskCard } from './HomiTaskCard';
import { HomiThinkingRow } from './HomiThinkingRow';

type Props = {
  messages: HomiMessage[];
  /** The real pending state of the turn: HOMI-D is resolving it. */
  isThinking?: boolean;
  /** The failure of the last turn, rendered inline (never as a modal). */
  errorMessage?: string | null;
  /** Retry is offered only when the failure is recoverable. */
  errorRetryable?: boolean;
  onRetry?: () => void;
  onDismissError?: () => void;
  /** Welcome state, rendered by the list itself so it scrolls with the turn rhythm. */
  emptyState?: React.ReactNode;
};

/** Width of a conversational bubble: the canvas stays visible on both sides. */
const BUBBLE_MAX_WIDTH = '86%';

/**
 * Conversation timeline of the DEMO V1 closure.
 *
 * Depth rule of the reference implementation, kept verbatim: only the user
 * turn is a surface. The assistant turn and the tool artifacts live directly
 * on the canvas, so the reading surface never competes with the reply.
 */
export function HomiMessageList({
  messages,
  isThinking = false,
  errorMessage = null,
  errorRetryable = false,
  onRetry,
  onDismissError,
  emptyState,
}: Props) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const reduceMotion = useReducedMotion();

  const listRef = useRef<FlatList<HomiMessage> | null>(null);
  const [showJump, setShowJump] = useState(false);
  const atBottomRef = useRef(true);

  const scrollToEnd = useCallback((animated = true) => {
    listRef.current?.scrollToEnd({ animated: animated && !reduceMotion });
  }, [reduceMotion]);

  // New content keeps the view anchored while the reader is at the bottom.
  useEffect(() => {
    if (atBottomRef.current) scrollToEnd();
  }, [messages.length, isThinking, errorMessage, scrollToEnd]);

  const handleScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distance = contentSize.height - contentOffset.y - layoutMeasurement.height;
    atBottomRef.current = distance <= 96;
    setShowJump((previous) => {
      const next = distance > 240;
      return next === previous ? previous : next;
    });
  }, []);

  const renderItem = useCallback(
    ({ item, index }: ListRenderItemInfo<HomiMessage>) => {
      const previous = index > 0 ? messages[index - 1] : null;
      const showIdentity =
        item.role === 'assistant' && (!previous || previous.role !== 'assistant' || previous.turn_id !== item.turn_id);
      return <MessageRow message={item} showIdentity={showIdentity} />;
    },
    [messages],
  );

  return (
    <View style={styles.container}>
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        contentContainerStyle={[styles.content, messages.length === 0 ? styles.contentEmpty : null]}
        onScroll={handleScroll}
        scrollEventThrottle={16}
        onContentSizeChange={() => {
          if (atBottomRef.current) scrollToEnd(false);
        }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        accessibilityLiveRegion="polite"
        ListEmptyComponent={emptyState ? <>{emptyState}</> : undefined}
        ListFooterComponent={isThinking ? <HomiThinkingRow /> : undefined}
      />

      {errorMessage ? (
        <View style={styles.errorContainer}>
          <View style={styles.errorRow} accessibilityLiveRegion="assertive" accessibilityRole="alert">
            <HomePlusIcon name="alert-circle-outline" size={18} color={theme.colors.danger.base} />
            <View style={styles.errorBody}>
              <AppText variant="bodySmall" weight="600" tone="danger">
                {errorMessage}
              </AppText>
              <View style={styles.errorActions}>
                {errorRetryable && onRetry ? (
                  <HomiPressable
                    onPress={onRetry}
                    accessibilityLabel="Reintentar"
                    style={styles.errorAction}
                  >
                    <AppText variant="caption" weight="700" tone="brand">
                      Reintentar
                    </AppText>
                  </HomiPressable>
                ) : null}
                {onDismissError ? (
                  <HomiPressable onPress={onDismissError} accessibilityLabel="Descartar el error" style={styles.errorAction}>
                    <AppText variant="caption" weight="700" tone="tertiary">
                      Descartar
                    </AppText>
                  </HomiPressable>
                ) : null}
              </View>
            </View>
          </View>
        </View>
      ) : null}

      {showJump ? (
        <HomiPressable
          onPress={() => scrollToEnd()}
          accessibilityLabel="Saltar a los mensajes nuevos"
          style={styles.jump}
        >
          <HomePlusIcon name="chevron-down" size={16} color={theme.colors.text.secondary} />
          <AppText variant="micro" weight="700" tone="secondary">
            Nuevos mensajes
          </AppText>
        </HomiPressable>
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// One turn
// ---------------------------------------------------------------------------

function MessageRow({ message, showIdentity }: { message: HomiMessage; showIdentity: boolean }) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const reduceMotion = useReducedMotion();
  const appear = useRef(new Animated.Value(reduceMotion ? 1 : 0)).current;
  const tasks = readTasks(message);
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const clock = homiFormatClock(message.created_at);

  useEffect(() => {
    if (reduceMotion) {
      appear.setValue(1);
      return;
    }
    const animation = Animated.timing(appear, {
      toValue: 1,
      duration: homiMotion.standard,
      easing: Easing.bezier(...homiEasing.in),
      useNativeDriver: true,
    });
    animation.start();
    return () => animation.stop();
  }, [appear, reduceMotion]);

  return (
    <Animated.View
      style={[
        styles.turn,
        isUser ? styles.turnUser : styles.turnAssistant,
        reduceMotion ? null : { opacity: appear },
      ]}
    >
      {showIdentity ? (
        <View style={styles.identity}>
          <HomePlusIcon name="sparkles" size={12} color={theme.colors.terracotta[700]} />
          <AppText variant="micro" weight="700" tone="brand">
            HOMI
          </AppText>
        </View>
      ) : null}

      {isSystem ? (
        <View style={styles.systemHeader}>
          <HomePlusIcon name="calendar-outline" size={14} color={theme.colors.text.secondary} />
          <AppText variant="micro" weight="700" tone="secondary">
            PLANNER
          </AppText>
        </View>
      ) : null}

      {message.attachment ? (
        <View
          style={[
            styles.attachmentRow,
            isUser ? styles.attachmentRowUser : styles.attachmentRowAssistant,
          ]}
        >
          <HomePlusIcon
            name={message.attachment.mime_type.startsWith('image/') ? 'image-outline' : 'document-text-outline'}
            size={18}
            color={theme.colors.text.secondary}
          />
          <View style={styles.attachmentBody}>
            <AppText variant="caption" weight="600" numberOfLines={1}>
              {message.attachment.original_filename}
            </AppText>
            {homiFormatFileSize(message.attachment.size_bytes) ? (
              <AppText variant="caption" tone="tertiary">
                {homiFormatFileSize(message.attachment.size_bytes)}
              </AppText>
            ) : null}
          </View>
        </View>
      ) : null}

      {isUser ? (
        <View
          accessibilityRole="text"
          accessibilityLabel={clock ? `${message.text}, ${clock}` : message.text}
          style={[
            styles.bubble,
            message.status === 'failed' && styles.bubbleFailed,
          ]}
        >
          <AppText variant="body" tone="primary">
            {message.text}
          </AppText>
          {message.status === 'pending' ? (
            <AppText variant="caption" tone="tertiary" style={styles.inlineNote}>
              Enviando…
            </AppText>
          ) : null}
          {message.see_result ? <SeeResultBlock seeResult={message.see_result} /> : null}
          {clock ? (
            <View style={styles.metaRow}>
              {message.via_voice ? (
                <HomePlusIcon name="mic-outline" size={12} color={theme.colors.text.muted} />
              ) : null}
              <AppText variant="micro" tone="muted">
                {clock}
              </AppText>
            </View>
          ) : null}
        </View>
      ) : (
        <View style={styles.assistantBlock}>
          <AppText
            variant="body"
            tone="primary"
            accessibilityRole="text"
            style={isSystem ? styles.systemText : styles.assistantText}
          >
            {message.text}
          </AppText>

          {message.see_result ? <SeeResultBlock seeResult={message.see_result} /> : null}

          {tasks.length > 0 ? (
            <View style={styles.taskList}>
              {tasks.map((task) => (
                <HomiTaskCard key={task.id} task={task} />
              ))}
            </View>
          ) : null}

          {clock ? (
            <View style={styles.metaRowAssistant}>
              {message.via_voice ? (
                <HomePlusIcon name="mic-outline" size={12} color={theme.colors.text.muted} />
              ) : null}
              <AppText variant="micro" tone="muted">
                {clock}
              </AppText>
            </View>
          ) : null}
        </View>
      )}
    </Animated.View>
  );
}

function SeeResultBlock({ seeResult }: { seeResult: NonNullable<HomiMessage['see_result']> }) {
  const theme = useHomiTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const warnings = seeResult.warnings ?? [];

  return (
    <View style={styles.seeBlock}>
      <View style={styles.seeHeader}>
        <HomePlusIcon
          name={seeResult.status === 'error' ? 'alert-circle-outline' : 'scan-outline'}
          size={14}
          color={seeResult.status === 'error' ? theme.colors.danger.base : theme.colors.text.secondary}
        />
        <AppText variant="caption" weight="600" tone="secondary">
          {seeResult.task}
        </AppText>
      </View>

      {warnings.map((warning, index) => (
        <View key={`${warning}-${index}`} style={styles.warningRow}>
          <HomePlusIcon name="warning-outline" size={13} color={theme.colors.warning.base} />
          <AppText variant="caption" tone="warning">
            {warning}
          </AppText>
        </View>
      ))}

      {seeResult.text ? (
        <AppText variant="caption" tone="secondary">
          {seeResult.text}
        </AppText>
      ) : null}

      {seeResult.status === 'error' && seeResult.message ? (
        <AppText variant="caption" tone="danger">
          {seeResult.message}
        </AppText>
      ) : null}
    </View>
  );
}

/** Reads the canonical task rows of a tool result, ignoring anything else. */
function readTasks(message: HomiMessage): HomiTaskDto[] {
  const result = message.tool_result?.result;
  if (!result || !Array.isArray(result.tasks)) return [];
  return result.tasks.filter(
    (task): task is HomiTaskDto =>
      typeof task === 'object' &&
      task !== null &&
      typeof (task as HomiTaskDto).id === 'string' &&
      typeof (task as HomiTaskDto).title === 'string',
  );
}

const makeStyles = (theme: HomiTheme) =>
  StyleSheet.create({
    container: {
      flex: 1,
    },
    content: {
      paddingHorizontal: theme.spacing[4],
      paddingTop: homiSpacing.headerToContent,
      paddingBottom: homiSpacing.composerGap,
    },
    contentEmpty: {
      flexGrow: 1,
      justifyContent: 'center',
    },
    turn: {
      marginBottom: homiSpacing.interTurn,
    },
    turnUser: {
      alignItems: 'flex-end',
    },
    turnAssistant: {
      alignItems: 'flex-start',
    },
    identity: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      marginBottom: 4,
    },
    systemHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      marginBottom: homiSpacing.rowGap,
    },
    // The user turn is the only surface of the conversation.
    bubble: {
      maxWidth: BUBBLE_MAX_WIDTH,
      paddingHorizontal: 14,
      paddingTop: 11,
      paddingBottom: 11,
      borderRadius: theme.radius.lg,
      borderBottomRightRadius: theme.radius.xs,
      backgroundColor: theme.colors.terracotta[50],
      gap: homiSpacing.rowGap,
    },
    bubbleFailed: {
      opacity: 0.72,
    },
    inlineNote: {
      marginTop: 2,
    },
    assistantBlock: {
      maxWidth: BUBBLE_MAX_WIDTH,
      gap: homiSpacing.rowGap,
    },
    assistantText: {
      lineHeight: 24,
    },
    systemText: {
      maxWidth: '100%',
    },
    attachmentRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.rowGap,
      marginBottom: homiSpacing.rowGap,
    },
    attachmentRowUser: {
      paddingBottom: homiSpacing.rowGap,
      borderBottomWidth: 1,
      borderBottomColor: 'rgba(26,24,22,0.08)',
    },
    attachmentRowAssistant: {},
    attachmentBody: {
      flex: 1,
    },
    seeBlock: {
      marginTop: 2,
      padding: homiSpacing.intraTurn,
      borderRadius: theme.radius.md,
      backgroundColor: theme.colors.surface.soft,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
      gap: 4,
    },
    seeHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
    },
    warningRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 4,
    },
    taskList: {
      gap: homiSpacing.rowGap,
      marginTop: 2,
    },
    metaRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: 4,
    },
    metaRowAssistant: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
    },
    // Inline error (H-ERR-01): icon + copy + action, always inside the flow.
    errorContainer: {
      paddingHorizontal: theme.spacing[4],
      paddingBottom: theme.spacing[2],
    },
    errorRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: homiSpacing.intraTurn,
      padding: homiSpacing.intraTurn,
      borderRadius: theme.radius.md,
      backgroundColor: theme.colors.danger.soft,
      borderWidth: 1,
      borderColor: theme.colors.danger.base,
    },
    errorBody: {
      flex: 1,
      gap: homiSpacing.rowGap,
    },
    errorActions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: homiSpacing.intraTurn,
    },
    errorAction: {
      minHeight: theme.touchTargets.normal,
      justifyContent: 'center',
    },
    jump: {
      position: 'absolute',
      right: theme.spacing[4],
      bottom: theme.spacing[2],
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      minHeight: 36,
      paddingHorizontal: theme.spacing[3],
      borderRadius: theme.radius.pill,
      backgroundColor: theme.colors.surface.card,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
      ...theme.shadows.card,
    },
  });
