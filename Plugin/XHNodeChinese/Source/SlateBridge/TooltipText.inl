// Translate known Niagara FText formats without splitting prose into words.
// Types, paths, compiled identifiers and numeric defaults keep their values.
static bool TranslateTooltipFormat(const FText& Text, bool Graph, FString& Out,
    TArray<FString>* Captured = nullptr, int Depth = 0) {
    if (Depth > 4) return false;
    TArray<FHistoricTextFormatData> History;
    FTextInspector::GetHistoricFormatData(Text, History);
    if (History.IsEmpty() || !History.Last().FormattedText.IdenticalTo(Text)) return false;
    const auto& Root = History.Last();
    const FString Pattern = Root.SourceFmt.GetSourceText().BuildSourceString();
    FFormatNamedArguments Args = Root.Arguments;
    FString Format;
    TArray<FString> Prose;
    bool Nested = false;
    if (Pattern == TEXT("{0}\n\nName: {1}\n\nType: {2}")) {
        Format = TEXT("{0}\n\n名称：{1}\n\n类型：{2}"); Prose = {TEXT("0"), TEXT("1")};
        if (!Args.Contains(TEXT("2"))) return false;
    } else if (Pattern == TEXT("Name: {0}\n\nType: {1}")) {
        Format = TEXT("名称：{0}\n\n类型：{1}"); Prose = {TEXT("0")};
        if (!Args.Contains(TEXT("1"))) return false;
    } else if (Pattern == TEXT("{0}\nMaterial Default: {1}")) {
        Format = TEXT("{0}\n材质默认值：{1}"); Nested = true;
        if (!Args.Contains(TEXT("1"))) return false;
    } else if (Pattern == TEXT("{0}\n\nCompiled Name: {1}")) {
        Format = TEXT("{0}\n\n编译名称：{1}"); Prose = {TEXT("0")};
        if (!Args.Contains(TEXT("1"))) return false;
    } else if (Pattern == TEXT("Compiled Name: {0}")) {
        Format = TEXT("编译名称：{0}");
        if (!Args.Contains(TEXT("0"))) return false;
    } else if (Pattern == TEXT("{1}\nPath: {0}{2}")) {
        Format = TEXT("{1}\n路径：{0}{2}"); Prose = {TEXT("1"), TEXT("2")};
        if (!Args.Contains(TEXT("0"))) return false;
    } else return false;
    if (Nested) {
        auto* Value = Args.Find(TEXT("0"));
        if (!Value || Value->GetType() != EFormatArgumentType::Text) return false;
        FString Translated;
        if (!TranslateTooltipFormat(Value->GetTextValue(), Graph, Translated, Captured, Depth + 1)) return false;
        *Value = FFormatArgumentValue(FText::FromString(Translated));
    }
    for (const auto& Key : Prose) {
        auto* Value = Args.Find(Key);
        if (!Value || Value->GetType() != EFormatArgumentType::Text) return false;
        const FString Source = Value->GetTextValue().ToString();
        if (Captured && !Source.IsEmpty()) Captured->Add(Source);
        const auto Translated = Graph ? GraphLookup(std::wstring(*Source)) : Lookup(std::wstring(*Source));
        if (Translated != std::wstring(*Source)) *Value = FFormatArgumentValue(FText::FromString(Translated.c_str()));
    }
    Out = FText::Format(FText::FromString(Format), Args).ToString();
    return true;
}

static std::wstring DisplayText(const FText& Text, bool Graph, bool Tooltip, bool Capture = false) {
    const FString Source = Text.ToString();
    auto Value = Graph ? GraphLookup(std::wstring(*Source)) : Lookup(std::wstring(*Source));
    // Complete user translations have precedence over translated components.
    if (Value != std::wstring(*Source)) return Value;
    FString Formatted;
    TArray<FString> Sources;
    if (Tooltip && TranslateTooltipFormat(Text, Graph, Formatted, Capture ? &Sources : nullptr)) {
        if (Capture) for (const auto& Part : Sources) CaptureSource(Part, Graph);
        return std::wstring(*Formatted);
    }
    if (Capture) CaptureSource(Source, Graph);
    return Value;
}
