import { useAppTheme } from '../context/AppThemeContext';
import { useThemeStyles } from '../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../constants/theme';
import React, { forwardRef, useState } from 'react';
import {
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  type StyleProp,
  type TextInputInstance,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { radius, spacing, typography } from '../constants/theme';

type AuthTextInputProps = TextInputProps & {
  label: string;
  error?: string | null;
  containerStyle?: StyleProp<ViewStyle>;
  isPasswordField?: boolean;
};

export const AuthTextInput = forwardRef<TextInputInstance, AuthTextInputProps>(
  ({ label, error, containerStyle, isPasswordField = false, style, ...props }, ref) => {
  const { colors, resolvedScheme } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

    const [isPasswordVisible, setIsPasswordVisible] = useState(false);
    const [isFocused, setIsFocused] = useState(false);
    const secureTextEntry = isPasswordField ? !isPasswordVisible : props.secureTextEntry;

    return (
      <View style={containerStyle}>
        <Text style={styles.label}>{label}</Text>
        <View
          style={[
            styles.inputContainer,
            isFocused ? styles.inputContainerFocused : null,
            error ? styles.inputContainerError : null,
            props.editable === false ? styles.inputContainerDisabled : null,
          ]}
        >
          <TextInput
            ref={ref}
            {...props}
              keyboardAppearance={props.keyboardAppearance ?? resolvedScheme}
            style={[styles.input, style]}
            placeholderTextColor={colors.text.muted}
            selectionColor={colors.brand}
            cursorColor={colors.text.primary}
            editable={props.editable}
            importantForAutofill="yes"
            secureTextEntry={secureTextEntry}
            onFocus={(event) => {
              setIsFocused(true);
              props.onFocus?.(event);
            }}
            onBlur={(event) => {
              setIsFocused(false);
              props.onBlur?.(event);
            }}
          />
          {isPasswordField ? (
            <TouchableOpacity
              style={styles.toggleButton}
              onPress={() => setIsPasswordVisible((current) => !current)}
              disabled={props.editable === false}
              accessibilityRole="button"
              accessibilityLabel={
                isPasswordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña'
              }
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Text style={styles.toggleText}>
                {isPasswordVisible ? 'Ocultar' : 'Mostrar'}
              </Text>
            </TouchableOpacity>
          ) : null}
        </View>
        {error ? <Text style={styles.errorText}>{error}</Text> : null}
      </View>
    );
  },
);

AuthTextInput.displayName = 'AuthTextInput';



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  label: {
    ...typography.bodySmall,
    color: colors.text.primary,
    marginBottom: spacing[2],
    marginLeft: spacing[1],
  },
  inputContainer: {
    backgroundColor: colors.surface.card,
    borderWidth: 1,
    borderColor: colors.border.default,
    borderRadius: radius.lg,
    minHeight: 56,
    paddingLeft: spacing[4],
    paddingRight: spacing[3],
    marginBottom: spacing[4],
    flexDirection: 'row',
    alignItems: 'center',
  },
  inputContainerFocused: {
    borderColor: colors.brand,
    backgroundColor: colors.surface.card,
  },
  inputContainerError: {
    borderColor: colors.danger.base,
    backgroundColor: colors.surface.card,
  },
  inputContainerDisabled: {
    backgroundColor: colors.surface.soft,
    borderColor: colors.border.default,
  },
  input: {
    flex: 1,
    paddingVertical: spacing[4],
    color: colors.text.primary,
    ...typography.body,
  },
  toggleButton: {
    justifyContent: 'center',
    alignItems: 'center',
    minWidth: 72,
    paddingVertical: 8,
    paddingLeft: 12,
  },
  toggleText: {
    color: colors.brandPressed,
    fontSize: 13,
    fontWeight: '600',
  },
  errorText: {
    color: colors.danger.text,
    fontSize: 13,
    marginTop: -4,
    marginBottom: 12,
    lineHeight: 18,
  },
});
}
