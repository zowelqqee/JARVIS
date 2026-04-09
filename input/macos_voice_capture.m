/* One-shot macOS speech capture helper for the JARVIS CLI. */

#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>
#import <Speech/Speech.h>
#include <signal.h>
#include <unistd.h>

static NSString *g_output_path = nil;
static NSString *g_error_path = nil;

static void emit_line(NSString *line, BOOL is_error) {
    NSString *payload = [line hasSuffix:@"\n"] ? line : [line stringByAppendingString:@"\n"];
    NSString *destination = is_error ? g_error_path : g_output_path;
    if (destination.length > 0) {
        NSError *write_error = nil;
        if ([payload writeToFile:destination atomically:YES encoding:NSUTF8StringEncoding error:&write_error]) {
            return;
        }
    }
    FILE *stream = is_error ? stderr : stdout;
    fprintf(stream, "%s", [payload UTF8String]);
    fflush(stream);
}

static int fail_with_message(NSString *code, NSString *message) {
    NSString *line = [NSString stringWithFormat:@"%@|%@", code ?: @"RECOGNITION_FAILED", message ?: @"Voice capture failed."];
    emit_line(line, YES);
    return 1;
}

static const char *signal_name(int sig) {
    switch (sig) {
        case SIGABRT:
            return "SIGABRT";
        case SIGSEGV:
            return "SIGSEGV";
        case SIGBUS:
            return "SIGBUS";
        case SIGILL:
            return "SIGILL";
        case SIGTRAP:
            return "SIGTRAP";
        default:
            return "SIGNAL";
    }
}

static void crash_signal_handler(int sig) {
    char buffer[256];
    int count = snprintf(buffer, sizeof(buffer), "VOICE_SETUP_FAILED|Voice helper crashed with %s.\n", signal_name(sig));
    if (count > 0) {
        write(STDERR_FILENO, buffer, (size_t)count);
    }
    _exit(1);
}

static void uncaught_exception_handler(NSException *exception) {
    NSString *reason = exception.reason ?: @"Unknown exception.";
    NSString *message = [NSString stringWithFormat:@"Uncaught Objective-C exception: %@ (%@)", exception.name, reason];
    fprintf(stderr, "VOICE_SETUP_FAILED|%s\n", [message UTF8String]);
    fflush(stderr);
}

static void install_crash_handlers(void) {
    NSSetUncaughtExceptionHandler(&uncaught_exception_handler);
    signal(SIGABRT, crash_signal_handler);
    signal(SIGSEGV, crash_signal_handler);
    signal(SIGBUS, crash_signal_handler);
    signal(SIGILL, crash_signal_handler);
    signal(SIGTRAP, crash_signal_handler);
}

static BOOL wait_for_flag_with_runloop(volatile BOOL *flag, NSTimeInterval timeout_seconds) {
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout_seconds];
    while (!(*flag) && [deadline timeIntervalSinceNow] > 0) {
        @autoreleasepool {
            [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        }
    }
    return *flag;
}

static BOOL request_speech_authorization(NSTimeInterval timeout, NSString **message) {
    __block SFSpeechRecognizerAuthorizationStatus status = [SFSpeechRecognizer authorizationStatus];
    if (status == SFSpeechRecognizerAuthorizationStatusNotDetermined) {
        __block volatile BOOL callback_done = NO;
        [SFSpeechRecognizer requestAuthorization:^(SFSpeechRecognizerAuthorizationStatus current_status) {
            status = current_status;
            callback_done = YES;
        }];

        if (!wait_for_flag_with_runloop(&callback_done, timeout)) {
            if (message != NULL) {
                *message = @"Timed out waiting for speech recognition permission.";
            }
            return NO;
        }
    }

    if (status == SFSpeechRecognizerAuthorizationStatusAuthorized) {
        return YES;
    }

    if (message == NULL) {
        return NO;
    }

    switch (status) {
        case SFSpeechRecognizerAuthorizationStatusDenied:
            *message = @"Speech recognition access was denied.";
            break;
        case SFSpeechRecognizerAuthorizationStatusRestricted:
            *message = @"Speech recognition is restricted on this Mac.";
            break;
        default:
            *message = @"Speech recognition is unavailable.";
            break;
    }
    return NO;
}

static BOOL request_microphone_authorization(NSTimeInterval timeout, NSString **message) {
    __block AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (status == AVAuthorizationStatusNotDetermined) {
        __block BOOL granted = NO;
        __block volatile BOOL callback_done = NO;
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL access_granted) {
            granted = access_granted;
            callback_done = YES;
        }];

        if (!wait_for_flag_with_runloop(&callback_done, timeout)) {
            if (message != NULL) {
                *message = @"Timed out waiting for microphone permission.";
            }
            return NO;
        }
        status = granted ? AVAuthorizationStatusAuthorized : AVAuthorizationStatusDenied;
    }

    if (status == AVAuthorizationStatusAuthorized) {
        return YES;
    }

    if (message == NULL) {
        return NO;
    }

    switch (status) {
        case AVAuthorizationStatusDenied:
            *message = @"Microphone access was denied.";
            break;
        case AVAuthorizationStatusRestricted:
            *message = @"Microphone access is restricted on this Mac.";
            break;
        default:
            *message = @"Microphone access is unavailable.";
            break;
    }
    return NO;
}

static BOOL probe_speech_authorization(NSString **message) {
    SFSpeechRecognizerAuthorizationStatus status = [SFSpeechRecognizer authorizationStatus];
    if (status == SFSpeechRecognizerAuthorizationStatusAuthorized) {
        return YES;
    }
    if (message == NULL) {
        return NO;
    }
    switch (status) {
        case SFSpeechRecognizerAuthorizationStatusNotDetermined:
            *message = @"Speech recognition permission has not been requested yet.";
            break;
        case SFSpeechRecognizerAuthorizationStatusDenied:
            *message = @"Speech recognition access was denied.";
            break;
        case SFSpeechRecognizerAuthorizationStatusRestricted:
            *message = @"Speech recognition is restricted on this Mac.";
            break;
        default:
            *message = @"Speech recognition is unavailable.";
            break;
    }
    return NO;
}

static BOOL probe_microphone_authorization(NSString **message) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (status == AVAuthorizationStatusAuthorized) {
        return YES;
    }
    if (message == NULL) {
        return NO;
    }
    switch (status) {
        case AVAuthorizationStatusNotDetermined:
            *message = @"Microphone permission has not been requested yet.";
            break;
        case AVAuthorizationStatusDenied:
            *message = @"Microphone access was denied.";
            break;
        case AVAuthorizationStatusRestricted:
            *message = @"Microphone access is restricted on this Mac.";
            break;
        default:
            *message = @"Microphone access is unavailable.";
            break;
    }
    return NO;
}

static NSArray<NSString *> *parse_preferred_locale_identifiers(NSString *raw_value) {
    if (raw_value.length == 0) {
        return @[];
    }

    NSMutableArray<NSString *> *identifiers = [NSMutableArray array];
    NSMutableSet<NSString *> *seen = [NSMutableSet set];
    NSCharacterSet *whitespace = [NSCharacterSet whitespaceAndNewlineCharacterSet];

    for (NSString *component in [raw_value componentsSeparatedByString:@","]) {
        NSString *identifier = [component stringByTrimmingCharactersInSet:whitespace];
        if (identifier.length == 0 || [seen containsObject:identifier]) {
            continue;
        }
        [seen addObject:identifier];
        [identifiers addObject:identifier];
    }
    return identifiers;
}

static SFSpeechRecognizer *recognizer_for_locale_identifier(NSString *identifier) {
    if (identifier.length == 0) {
        return nil;
    }

    NSLocale *locale = [NSLocale localeWithLocaleIdentifier:identifier];
    SFSpeechRecognizer *recognizer = [[SFSpeechRecognizer alloc] initWithLocale:locale];
    if (recognizer != nil && recognizer.available) {
        return recognizer;
    }
    return nil;
}

static SFSpeechRecognizer *build_command_recognizer(NSArray<NSString *> *preferred_locale_identifiers) {
    for (NSString *identifier in preferred_locale_identifiers) {
        SFSpeechRecognizer *preferred_recognizer = recognizer_for_locale_identifier(identifier);
        if (preferred_recognizer != nil) {
            return preferred_recognizer;
        }
    }

    NSString *current_locale_identifier = [[NSLocale currentLocale] localeIdentifier];
    SFSpeechRecognizer *current_recognizer = recognizer_for_locale_identifier(current_locale_identifier);
    if (current_recognizer != nil) {
        return current_recognizer;
    }

    SFSpeechRecognizer *default_recognizer = [[SFSpeechRecognizer alloc] init];
    if (default_recognizer != nil && default_recognizer.available) {
        return default_recognizer;
    }

    return nil;
}

static BOOL validate_privacy_usage_descriptions(NSString **message) {
    NSBundle *bundle = [NSBundle mainBundle];
    NSString *speech_description = [bundle objectForInfoDictionaryKey:@"NSSpeechRecognitionUsageDescription"];
    NSString *microphone_description = [bundle objectForInfoDictionaryKey:@"NSMicrophoneUsageDescription"];

    if (speech_description.length == 0) {
        if (message != NULL) {
            *message = @"Voice helper is missing NSSpeechRecognitionUsageDescription.";
        }
        return NO;
    }

    if (microphone_description.length == 0) {
        if (message != NULL) {
            *message = @"Voice helper is missing NSMicrophoneUsageDescription.";
        }
        return NO;
    }

    return YES;
}

static int first_user_argument_index(int argc, const char *argv[]) {
    int argument_index = 1;
    while (argc > argument_index) {
        const char *candidate = argv[argument_index];
        if (candidate == NULL) {
            argument_index += 1;
            continue;
        }
        if (strncmp(candidate, "-psn_", 5) == 0) {
            argument_index += 1;
            continue;
        }
        if (strcmp(candidate, "-ApplePersistenceIgnoreState") == 0) {
            argument_index += 1;
            if (argc > argument_index) {
                argument_index += 1;
            }
            continue;
        }
        if (strcmp(candidate, "-NSDocumentRevisionsDebugMode") == 0) {
            argument_index += 1;
            if (argc > argument_index) {
                argument_index += 1;
            }
            continue;
        }
        break;
    }
    return argument_index;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        install_crash_handlers();

        if (!NSApplicationLoad()) {
            return fail_with_message(@"VOICE_SETUP_FAILED", @"Unable to load macOS application runtime for voice capture.");
        }

        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];

        int argument_index = first_user_argument_index(argc, argv);

        if (argc > argument_index && strcmp(argv[argument_index], "--probe-permissions") == 0) {
            NSString *privacy_message = nil;
            if (!validate_privacy_usage_descriptions(&privacy_message)) {
                return fail_with_message(@"VOICE_SETUP_FAILED", privacy_message ?: @"Voice helper privacy usage descriptions are missing.");
            }

            NSString *authorization_message = nil;
            if (!probe_speech_authorization(&authorization_message)) {
                SFSpeechRecognizerAuthorizationStatus status = [SFSpeechRecognizer authorizationStatus];
                if (status == SFSpeechRecognizerAuthorizationStatusNotDetermined) {
                    return fail_with_message(@"PERMISSION_PROMPT_REQUIRED", authorization_message ?: @"Speech recognition permission has not been requested yet.");
                }
                return fail_with_message(@"PERMISSION_DENIED", authorization_message ?: @"Speech recognition access is unavailable.");
            }

            if (!probe_microphone_authorization(&authorization_message)) {
                AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
                if (status == AVAuthorizationStatusNotDetermined) {
                    return fail_with_message(@"PERMISSION_PROMPT_REQUIRED", authorization_message ?: @"Microphone permission has not been requested yet.");
                }
                return fail_with_message(@"MICROPHONE_UNAVAILABLE", authorization_message ?: @"Microphone access is unavailable.");
            }

            emit_line(@"VOICE_CAPTURE_PERMISSIONS_OK", NO);
            return 0;
        }

        NSTimeInterval timeout = 8.0;
        NSString *preferred_locales_argument = nil;
        if (argc > argument_index) {
            timeout = MAX(2.0, atof(argv[argument_index]));
        }
        if (argc > argument_index + 1) {
            preferred_locales_argument = [NSString stringWithUTF8String:argv[argument_index + 1]];
        }
        if (argc > argument_index + 2) {
            g_output_path = [NSString stringWithUTF8String:argv[argument_index + 2]];
        }
        if (argc > argument_index + 3) {
            g_error_path = [NSString stringWithUTF8String:argv[argument_index + 3]];
        }

        NSString *privacy_message = nil;
        if (!validate_privacy_usage_descriptions(&privacy_message)) {
            return fail_with_message(@"VOICE_SETUP_FAILED", privacy_message ?: @"Voice helper privacy usage descriptions are missing.");
        }

        NSString *authorization_message = nil;
        if (!request_speech_authorization(timeout, &authorization_message)) {
            return fail_with_message(@"PERMISSION_DENIED", authorization_message ?: @"Speech recognition access is unavailable.");
        }

        if (!request_microphone_authorization(timeout, &authorization_message)) {
            return fail_with_message(@"MICROPHONE_UNAVAILABLE", authorization_message ?: @"Microphone access is unavailable.");
        }

        NSArray<NSString *> *preferred_locale_identifiers = parse_preferred_locale_identifiers(preferred_locales_argument);
        SFSpeechRecognizer *recognizer = build_command_recognizer(preferred_locale_identifiers);
        if (recognizer == nil) {
            return fail_with_message(@"RECOGNITION_FAILED", @"Speech recognition is not available right now.");
        }

        AVAudioEngine *audio_engine = [[AVAudioEngine alloc] init];
        AVAudioInputNode *input_node = [audio_engine inputNode];
        if (input_node == nil) {
            return fail_with_message(@"MICROPHONE_UNAVAILABLE", @"No microphone input device is available.");
        }

        SFSpeechAudioBufferRecognitionRequest *request = [[SFSpeechAudioBufferRecognitionRequest alloc] init];
        request.shouldReportPartialResults = YES;
        request.taskHint = SFSpeechRecognitionTaskHintDictation;

        AVAudioFormat *recording_format = [input_node outputFormatForBus:0];
        __block NSUInteger captured_buffer_count = 0;
        [input_node installTapOnBus:0
                         bufferSize:1024
                             format:recording_format
                              block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
                                  captured_buffer_count += 1;
                                  [request appendAudioPCMBuffer:buffer];
                              }];

        NSError *audio_error = nil;
        [audio_engine prepare];
        if (![audio_engine startAndReturnError:&audio_error]) {
            [input_node removeTapOnBus:0];
            return fail_with_message(@"MICROPHONE_UNAVAILABLE", audio_error.localizedDescription ?: @"Unable to start microphone capture.");
        }

        __block NSString *recognized_text = nil;
        __block NSString *latest_partial_text = nil;
        __block NSString *recognition_message = nil;
        __block volatile BOOL finished = NO;

        __block SFSpeechRecognitionTask *task = [recognizer recognitionTaskWithRequest:request
                                                                          resultHandler:^(SFSpeechRecognitionResult *result, NSError *error) {
                                                                              if (result != nil) {
                                                                                  NSString *current_text = result.bestTranscription.formattedString;
                                                                                  if (current_text.length > 0) {
                                                                                      latest_partial_text = current_text;
                                                                                  }
                                                                              }
                                                                              if (result != nil && result.isFinal) {
                                                                                  recognized_text = result.bestTranscription.formattedString;
                                                                                  finished = YES;
                                                                              }
                                                                              if (error != nil) {
                                                                                  recognition_message = error.localizedDescription ?: @"Speech recognition failed.";
                                                                                  finished = YES;
                                                                              }
                                                                          }];

        BOOL completed_in_time = wait_for_flag_with_runloop(&finished, timeout);
        if (!completed_in_time) {
            if (captured_buffer_count == 0) {
                recognition_message = @"No microphone audio was captured during listening.";
            } else {
                recognition_message = @"Timed out waiting for speech input.";
            }
        }

        [audio_engine stop];
        [request endAudio];
        [input_node removeTapOnBus:0];

        if (!finished) {
            (void)wait_for_flag_with_runloop(&finished, 1.0);
        }

        [task cancel];

        if (recognized_text.length == 0 && latest_partial_text.length > 0) {
            recognized_text = latest_partial_text;
        }

        if (recognized_text.length > 0) {
            emit_line(recognized_text, NO);
            return 0;
        }

        if (recognition_message.length == 0) {
            recognition_message = @"No speech was recognized.";
        }
        return fail_with_message(@"EMPTY_RECOGNITION", recognition_message);
    }
}
