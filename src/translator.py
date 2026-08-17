from __future__ import annotations

import argostranslate.package
import argostranslate.translate

SOURCE_LANGUAGE = "en"
TARGET_LANGUAGE = "pb"


def ensure_translation_model() -> None:
    installed = argostranslate.package.get_installed_packages()
    if any(p.from_code == SOURCE_LANGUAGE and p.to_code == TARGET_LANGUAGE for p in installed):
        return

    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    package = next((p for p in available if p.from_code == SOURCE_LANGUAGE and p.to_code == TARGET_LANGUAGE), None)
    if package is None:
        raise RuntimeError("English → Portuguese (Brazil) Argos model was not found.")
    package.install()


def translate_text(text: str) -> str:
    ensure_translation_model()
    languages = argostranslate.translate.get_installed_languages()
    source = next((language for language in languages if language.code == SOURCE_LANGUAGE), None)
    target = next((language for language in languages if language.code == TARGET_LANGUAGE), None)
    if source is None or target is None:
        raise RuntimeError("Required Argos languages are not installed.")
    translation = source.get_translation(target)
    if translation is None:
        raise RuntimeError("No English → Portuguese (Brazil) translation is installed.")
    result = translation.translate(text).strip()
    if not result:
        raise RuntimeError("Translation returned empty text.")
    return result
