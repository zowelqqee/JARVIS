/* One-shot macOS speech capture helper for the JARVIS CLI. */

#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>
#import <Speech/Speech.h>

static int fail_with_message(NSString *code, NSString *message) {
    fprintf(stderr, "%s|%s\n", [code UTF8String], [message UTF8String]);
    return 1;
}

static BOOL request_speech_authorization(NSTimeInterval timeout, NSString **message) {
    __block SFSpeechRecognizerAuthorizationStatus status = [SFSpeechRecognizer authorizationStatus];
    if (status == SFSpeechRecognizerAuthorizationStatusNotDetermined) {
        dispatch_semaphore_t wait_semaphore = dispatch_semaphore_create(0);
        [SFSpeechRecognizer requestAuthorization:^(SFSpeechRecognizerAuthorizationStatus current_status) {
            status = current_status;
            dispatch_semaphore_signal(wait_semaphore);
        }];

        dispatch_time_t deadline = dispatch_time(DISPATCH_TIME_NOW, (int64_t)(timeout * NSEC_PER_SEC));
        if (dispatch_semaphore_wait(wait_semaphore, deadline) != 0) {
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
        dispatch_semaphore_t wait_semaphore = dispatch_semaphore_create(0);
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL access_granted) {
            granted = access_granted;
            dispatch_semaphore_signal(wait_semaphore);
        }];

        dispatch_time_t deadline = dispatch_time(DISPATCH_TIME_NOW, (int64_t)(timeout * NSEC_PER_SEC));
        if (dispatch_semaphore_wait(wait_semaphore, deadline) != 0) {
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

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSTimeInterval timeout = 8.0;
        if (argc > 1) {
            timeout = MAX(2.0, atof(argv[1]));
        }

        NSString *authorization_message = nil;
        if (!request_speech_authorization(timeout, &authorization_message)) {
            return fail_with_message(@"PERMISSION_DENIED", authorization_message ?: @"Speech recognition access is unavailable.");
        }

        if (!request_microphone_authorization(timeout, &authorization_message)) {
            return fail_with_message(@"MICROPHONE_UNAVAILABLE", authorization_message ?: @"Microphone access is unavailable.");
        }

        NSLocale *locale = [NSLocale currentLocale];
        SFSpeechRecognizer *recognizer = [[SFSpeechRecognizer alloc] initWithLocale:locale];
        if (recognizer == nil) {
            recognizer = [[SFSpeechRecognizer alloc] init];
        }
        if (recognizer == nil || !recognizer.available) {
            return fail_with_message(@"RECOGNITION_FAILED", @"Speech recognition is not available right now.");
        }

        AVAudioEngine *audio_engine = [[AVAudioEngine alloc] init];
        AVAudioInputNode *input_node = [audio_engine inputNode];
        if (input_node == nil) {
            return fail_with_message(@"MICROPHONE_UNAVAILABLE", @"No microphone input device is available.");
        }

        SFSpeechAudioBufferRecognitionRequest *request = [[SFSpeechAudioBufferRecognitionRequest alloc] init];
        request.shouldReportPartialResults = NO;

        AVAudioFormat *recording_format = [input_node outputFormatForBus:0];
        [input_node installTapOnBus:0
                         bufferSize:1024
                             format:recording_format
                              block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
                                  [request appendAudioPCMBuffer:buffer];
                              }];

        NSError *audio_error = nil;
        [audio_engine prepare];
        if (![audio_engine startAndReturnError:&audio_error]) {
            [input_node removeTapOnBus:0];
            return fail_with_message(@"MICROPHONE_UNAVAILABLE", audio_error.localizedDescription ?: @"Unable to start microphone capture.");
        }

        __block NSString *recognized_text = nil;
        __block NSString *recognition_message = nil;
        __block BOOL finished = NO;
        dispatch_semaphore_t wait_semaphore = dispatch_semaphore_create(0);

        __block SFSpeechRecognitionTask *task = [recognizer recognitionTaskWithRequest:request
                                                                          resultHandler:^(SFSpeechRecognitionResult *result, NSError *error) {
                                                                              if (result != nil && result.isFinal) {
                                                                                  recognized_text = result.bestTranscription.formattedString;
                                                                                  if (!finished) {
                                                                                      finished = YES;
                                                                                      dispatch_semaphore_signal(wait_semaphore);
                                                                                  }
                                                                              }
                                                                              if (error != nil) {
                                                                                  recognition_message = error.localizedDescription ?: @"Speech recognition failed.";
                                                                                  if (!finished) {
                                                                                      finished = YES;
                                                                                      dispatch_semaphore_signal(wait_semaphore);
                                                                                  }
                                                                              }
                                                                          }];

        dispatch_time_t deadline = dispatch_time(DISPATCH_TIME_NOW, (int64_t)(timeout * NSEC_PER_SEC));
        if (dispatch_semaphore_wait(wait_semaphore, deadline) != 0) {
            recognition_message = @"Timed out waiting for speech input.";
        }

        [audio_engine stop];
        [request endAudio];
        [input_node removeTapOnBus:0];
        [task cancel];

        if (recognized_text.length > 0) {
            printf("%s\n", [recognized_text UTF8String]);
            return 0;
        }

        if (recognition_message.length == 0) {
            recognition_message = @"No speech was recognized.";
        }
        return fail_with_message(@"EMPTY_RECOGNITION", recognition_message);
    }
}
