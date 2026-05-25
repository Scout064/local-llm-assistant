class TestSTTImports:
    def test_module_imports(self):
        from src.voice.stt import transcribe, transcribe_file
        assert callable(transcribe)
        assert callable(transcribe_file)