// Run only in an isolated editor, alongside the existing restoration tests.
XH_EXPORT int XH_TooltipSelfTest() {
    if (!IsInGameThread() || !FSlateApplication::IsInitialized()) return -1;
    XH_Clear(); XH_Enable(1,0); XH_Collect(0);
    const FText Description=FText::FromString(TEXT("Controls the fixture's force. Preserve {Value} and Transient.PhysicsForce."));
    const FText Name=FText::FromString(TEXT("Vortex Origin Offset"));
    const FText Type=FText::FromString(TEXT("ENiagaraRestitutionMergeType"));
    const FString Chinese(TEXT("控制测试力，保留 {Value} 和 Transient.PhysicsForce。"));
    XH_Add(*Description.ToString(),*Chinese);XH_Add(*Name.ToString(),TEXT("涡旋原点偏移"));
    XH_Add(*Type.ToString(),TEXT("此译文不应覆盖类型标识符"));
    const FText Original=FNiagaraEditorUtilities::FormatVariableDescription(Description,Name,Type);
    const FString Expected=Chinese+TEXT("\n\n名称：涡旋原点偏移\n\n类型：ENiagaraRestitutionMergeType");
    if(DisplayText(Original,false,true)!=std::wstring(*Expected))return 401;
    // Format history remains intact in a real tooltip; translated locres may
    // contain extra backslashes, which must not prevent argument translation.
    FText Live=Original;
    auto Label=SNew(STextBlock).Text_Lambda([&Live](){return Live;});
    auto Tip=SNew(SToolTip)[Label];
    FSlateApplication::Get().SpawnToolTip(Tip,FVector2f(100,100));XH_Tick();
    if(Label->GetText().ToString()!=Expected)return 402;
    FSlateApplication::Get().CloseToolTip();
    auto Plain=SNew(STextBlock).Text(Original);VisitWidget(Plain);
    if(Plain->GetText().ToString()!=Original.ToString())return 403;
    auto Rich=SNew(SRichTextBlock).Text(Original);VisitWidget(SNew(SToolTip)[Rich]);
    if(Rich->GetText().ToString()!=Expected)return 404;
    const FText NoDesc=FNiagaraEditorUtilities::FormatVariableDescription(FText(),Name,Type);
    Live=NoDesc;
    if(Label->GetText().ToString()!=TEXT("名称：涡旋原点偏移\n\n类型：ENiagaraRestitutionMergeType"))return 405;
    const FText Default=FText::AsNumber(0.25);
    const FText Nested=FText::Format(FText::FromString(TEXT("{0}\nMaterial Default: {1}")),Original,Default);
    if(DisplayText(Nested,false,true)!=std::wstring(*(Expected+TEXT("\n材质默认值：")+Default.ToString())))return 406;
    const FText Path=FText::FromString(TEXT("/Niagara/Modules/Collision/Collision.Collision"));
    XH_Add(*Path.ToString(),TEXT("此译文不应覆盖路径"));
    const FText AssetTip=FText::Format(FText::FromString(TEXT("{1}\nPath: {0}{2}")),Path,Description,FText());
    if(DisplayText(AssetTip,false,true)!=std::wstring(*(Chinese+TEXT("\n路径：")+Path.ToString())))return 407;
    const FText Compiled=FText::Format(FText::FromString(TEXT("{0}\n\nCompiled Name: {1}")),Description,Type);
    if(DisplayText(Compiled,false,true)!=std::wstring(*(Chinese+TEXT("\n\n编译名称：")+Type.ToString())))return 408;
    XH_Collect(1);PendingCapture.clear();PendingKeys.clear();Observed.clear();
    const FString Unknown(TEXT("UnknownFixtureExplanation: The coefficient changes this entire sentence."));
    const FText UnknownTip=FNiagaraEditorUtilities::FormatVariableDescription(FText::FromString(Unknown),Name,Type);
    DisplayText(UnknownTip,false,true,true);
    if(PendingCapture.size()!=1 || PendingCapture[0]!=std::wstring(*Unknown))return 409;
    const FText Arbitrary=FText::Format(FText::FromString(TEXT("Code {0}: {1}")),Name,Type);
    if(DisplayText(Arbitrary,false,true)!=std::wstring(*Arbitrary.ToString()))return 410;
    XH_Add(*Original.ToString(),TEXT("个人完整提示优先"));
    if(DisplayText(Original,false,true)!=L"个人完整提示优先")return 411;
    XH_Enable(0,0);
    if(Label->GetText().ToString()!=NoDesc.ToString() || Rich->GetText().ToString()!=Original.ToString())return 412;
    XH_Collect(0);XH_Clear();PendingCapture.clear();PendingKeys.clear();Observed.clear();
    return 0;
}
