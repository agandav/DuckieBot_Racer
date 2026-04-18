# https://azure.microsoft.com/en-us/products/ai-services/speech-to-text
# https://github.com/Azure-Samples/cognitive-services-speech-sdk
# https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-to-text
# https://github.com/Azure-Samples/cognitive-services-speech-sdk/tree/master/quickstart/python/from-microphone
# venv/bin/pip install azure-cognitiveservices-speech
import azure.cognitiveservices.speech as speechsdk
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import keys
listen = True
recognized_text = None
stop_recognition = False
speech_recognizer = None
_on_recognized_callback = None


def set_up(on_recognized=None):
    global speech_recognizer, _on_recognized_callback
    _on_recognized_callback = on_recognized

    speech_config = speechsdk.SpeechConfig(
        subscription=keys.azure_key,
        region=keys.azure_region)
    speech_config.speech_recognition_language = "en-US"

    # ---------------------------------------------------------------------------
    # Latency optimizations
    # ---------------------------------------------------------------------------
    # How long to wait after speech stops before firing recognized event
    # Default is 1500ms — reduced to 500ms for faster response
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
        "500"
    )
    # How long to wait for speech to start before giving up
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
        "5000"
    )

    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)

    # Continuous recognition — fires on every recognized chunk, no restart gap
    def on_recognized_handler(evt):
        global recognized_text
        if not listen:
            return  # ignore while we are speaking
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            recognized_text = evt.result.text
            if _on_recognized_callback:
                _on_recognized_callback(evt.result.text)

    def on_canceled_handler(evt):
        details = evt.result.cancellation_details
        print("Speech recognition canceled: {}".format(details.reason))
        if details.reason == speechsdk.CancellationReason.Error:
            print("Error details: {}".format(details.error_details))

    speech_recognizer.recognized.connect(on_recognized_handler)
    speech_recognizer.canceled.connect(on_canceled_handler)


def start(on_recognized=None):
    global stop_recognition
    stop_recognition = False
    if speech_recognizer is None:
        set_up(on_recognized)
    speech_recognizer.start_continuous_recognition()


def stop():
    global stop_recognition
    stop_recognition = True
    if speech_recognizer:
        speech_recognizer.stop_continuous_recognition()


if __name__ == "__main__":
    set_up()
    start()
    print("Listening... speak now. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.1)
            if recognized_text:
                print("Recognized: {}".format(recognized_text))
                recognized_text = None
    except KeyboardInterrupt:
        stop()