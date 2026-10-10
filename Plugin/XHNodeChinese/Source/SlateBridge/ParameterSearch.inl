// Search-only aliases. Never modify a Niagara variable, namespace, or asset.
struct FParameterSearchBinding {
    TWeakPtr<SNiagaraParameterPanelSelector> Selector;
    void* ModelIdentity=nullptr;
    SNiagaraParameterPanelSelector::FOnDoesItemMatchFilterText Original;
    FDelegateHandle Handle;
    uint64 AppliedRevision=~uint64(0);
    TMap<FString,FString> Aliases;
};
static TMap<SNiagaraParameterPanelSelector*,TSharedPtr<FParameterSearchBinding>> ParameterBindings;

static FString ParameterAliases(const FNiagaraParameterPanelItem& Item) {
    if(!Item.ScriptVariable)return FString();
    const FString Name=Item.GetVariable().GetName().ToString();
    TArray<FString> Parts;Name.ParseIntoArray(Parts,TEXT("."),true);
    TArray<FString> Aliases;
    auto Add=[&](const FString& S){
        if(S.IsEmpty())return;
        for(const auto& Alias:SearchAliases(S))Aliases.AddUnique(Alias);
        for(const auto& Alias:SearchAliases(FString(Lookup(*S).c_str())))Aliases.AddUnique(Alias);
    };
    Add(Name);
    FString Joined,Translated;
    for(const FString& Part:Parts){
        const FString Display=FName::NameToDisplayString(Part,false);
        Add(Part);Add(Display);
        auto Local=Lookup(*Part);
        if(Local==std::wstring(*Part))Local=Lookup(*Display);
        Joined+=Display;Translated+=FString(Local.c_str());
    }
    Add(Joined);Add(Translated);
    Add(Item.NamespaceMetaData.DisplayName.ToString());
    Add(Item.NamespaceMetaData.DisplayNameLong.ToString());
    return FString::Join(Aliases,TEXT("\n"));
}
static bool ParameterMatches(FParameterSearchBinding& B,const FText& Query,const FNiagaraParameterPanelItem& Item){
    if(B.Original.IsBound() && B.Original.Execute(Query,Item))return true;
    if(!Enabled || !Item.ScriptVariable)return false;
    if(B.AppliedRevision!=Revision){B.Aliases.Empty();B.AppliedRevision=Revision;}
    const FString Key=Item.GetVariable().GetName().ToString()+TEXT("\n")+Item.NamespaceMetaData.DisplayName.ToString()+TEXT("\n")+Item.NamespaceMetaData.DisplayNameLong.ToString();
    auto* Aliases=B.Aliases.Find(Key);
    if(!Aliases){
        if(B.Aliases.Num()>10000)B.Aliases.Empty();
        Aliases=&B.Aliases.Add(Key,ParameterAliases(Item));
    }
    TArray<FString> Terms;FString(Normalize(*Query.ToString()).Text.c_str()).ParseIntoArray(Terms,TEXT(" "),true);
    for(const auto& Term:Terms)if(!Aliases->Contains(Term,ESearchCase::IgnoreCase))return false;
    return true;
}
static void RestoreParameterBinding(FParameterSearchBinding& B){
    if(auto Selector=B.Selector.Pin()){
        auto* Filter=ParameterFilter(*Selector);
        if(Filter && ParameterModelIdentity(*Selector)==B.ModelIdentity && Filter->GetHandle()==B.Handle)*Filter=B.Original;
    }
}
static void RestoreParameterSearch(){
    for(auto& Pair:ParameterBindings){
        RestoreParameterBinding(*Pair.Value);
        if(auto Selector=Pair.Value->Selector.Pin())if(Selector->IsSearching())Selector->RefreshAllCurrentItems();
    }
    ParameterBindings.Empty();
}
static void IndexParameterSelector(const TSharedRef<SNiagaraParameterPanelSelector>& Selector){
    if(!Enabled)return;
    auto* FilterPtr=ParameterFilter(Selector.Get());if(!FilterPtr)return;
    auto& Filter=*FilterPtr;
    auto Model=ParameterModelIdentity(Selector.Get());
    auto* Existing=ParameterBindings.Find(&Selector.Get());
    if(Existing && (*Existing)->ModelIdentity==Model && Filter.GetHandle()==(*Existing)->Handle){
        if((*Existing)->AppliedRevision!=Revision){
            (*Existing)->Aliases.Empty();(*Existing)->AppliedRevision=Revision;
            if(Selector->IsSearching())Selector->RefreshAllCurrentItems();
        }
        return;
    }
    if(Existing)RestoreParameterBinding(**Existing);
    auto B=MakeShared<FParameterSearchBinding>();
    B->Selector=Selector;B->ModelIdentity=Model;B->Original=Filter;B->AppliedRevision=Revision;
    auto Wrapped=SNiagaraParameterPanelSelector::FOnDoesItemMatchFilterText::CreateLambda(
        [B](const FText& Query,const FNiagaraParameterPanelItem& Item){return ParameterMatches(*B,Query,Item);});
    B->Handle=Wrapped.GetHandle();Filter=Wrapped;
    ParameterBindings.Add(&Selector.Get(),B);
    if(Selector->IsSearching())Selector->RefreshAllCurrentItems();
}
