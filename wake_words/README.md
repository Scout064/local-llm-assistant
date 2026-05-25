# Custom Wake Word Models

Place `.onnx` model files in this directory. To use one, set the `voice.wake_word.model`
path in `config/settings.yaml` to point to the file (e.g. `wake_words/my_phrase.onnx`).

## Training Custom Models

openwakeword supports training custom wake phrases. See the official documentation:

<https://github.com/davidburbery/openwakeword>

1. Collect audio samples of your target phrase
2. Use openwakeword's training script to generate an `.onnx` model
3. Place the resulting `.onnx` file in this `wake_words/` directory
4. Update `config/settings.yaml` → `voice.wake_word.model` to the file path

## Built-in Models

The following built-in model names can be used directly (no `.onnx` file needed):

- `hey_jarvis`
- `alexa`
- `hey_mycroft`
- `hey_rhasspy`

These are downloaded automatically on first use to `~/.local/share/openwakeword/`.