// Run in disposable editors only: these tests temporarily replace the dictionary.
XH_EXPORT int XH_LabelSelfTest() {
    if(!IsInGameThread() || !FSlateApplication::IsInitialized())return -1;
    XH_Clear();XH_Enable(1,0);XH_Collect(0);
    XH_Add(L"Combined Collision Normal",L"合并碰撞法线");
    XH_Add(L"Physics Collides This Frame",L"本帧发生物理碰撞");
    XH_Add(L"Module Collision {Index} Normal",L"模块碰撞 {Index} 法线");
    XH_Add(L"Dynamic Material Parameter",L"动态材质参数");
    const std::pair<const wchar_t*,const wchar_t*> Cases[]={
        {L"CombinedCollisionNormal",L"合并碰撞法线"},
        {L"combinedcollisionnormal",L"合并碰撞法线"},
        {L"Combined Collision Normal",L"合并碰撞法线"},
        {L"PhysicsCollidesThisFrame",L"本帧发生物理碰撞"},
        {L"ModuleCollision 1 Normal",L"模块碰撞 1 法线"},
        {L"ModuleCollision2Normal",L"模块碰撞 2 法线"},
        {L"Module Collision 001 Normal",L"模块碰撞 001 法线"},
        {L"ModuleCollision12Normal",L"模块碰撞 12 法线"},
        {L"DynamicMaterialParameter2",L"动态材质参数 2"},
    };
    for(int I=0;I<UE_ARRAY_COUNT(Cases);++I)if(Lookup(Cases[I].first)!=Cases[I].second)return 601+I;
    for(const wchar_t* S:{L"Output.Collision.CombinedCollisionNormal",L"/Game/CombinedCollisionNormal",L"CombinedCollisionNormal()",L"CombinedCollisionNormal = 1",L"ModuleCollision1Normal2",L"ModuleCollision-1Normal",L"Vector3",L"float4",L"Texture2D",L"{CombinedCollisionNormal}",L"A sentence with CombinedCollisionNormal."})
        if(Lookup(S)!=S)return 620;
    FString Live(TEXT("ModuleCollision 1 Normal"));
    auto Label=SNew(STextBlock).Text_Lambda([&Live](){return FText::FromString(Live);});
    VisitWidget(Label);if(Label->GetText().ToString()!=TEXT("模块碰撞 1 法线"))return 621;
    Live=TEXT("ModuleCollision2Normal");if(Label->GetText().ToString()!=TEXT("模块碰撞 2 法线"))return 622;
    auto* Variable=NewObject<UNiagaraScriptVariable>();
    Variable->Variable=FNiagaraVariable(FNiagaraTypeDefinition::GetFloatDef(),TEXT("Output.Collision.ModuleCollision2Normal"));
    FNiagaraParameterPanelItem Item;Item.ScriptVariable=Variable;
    FParameterSearchBinding Binding;
    for(const TCHAR* Q:{TEXT("模块碰撞 2 法线"),TEXT("ModuleCollision2Normal"),TEXT("Module Collision 2 Normal")})
        if(!ParameterMatches(Binding,FText::FromString(Q),Item))return 623;
    XH_Add(L"Combined Collision Normal",L"用户合并法线");
    if(Lookup(L"CombinedCollisionNormal")!=L"用户合并法线")return 624;
    XH_Add(L"ModuleCollision2Normal",L"用户二号法线");
    if(Label->GetText().ToString()!=TEXT("用户二号法线"))return 625;
    XH_Add(L"AB C",L"甲");XH_Add(L"A BC",L"乙");
    if(Lookup(L"ABC")!=L"ABC" || Lookup(L"AB C")!=L"甲")return 626;
    XH_Enable(0,0);
    if(Label->GetText().ToString()!=Live || Item.GetVariable().GetName()!=FName(TEXT("Output.Collision.ModuleCollision2Normal")))return 627;
    XH_Clear();if(Lookup(L"CombinedCollisionNormal")!=L"CombinedCollisionNormal")return 628;
    return 0;
}
