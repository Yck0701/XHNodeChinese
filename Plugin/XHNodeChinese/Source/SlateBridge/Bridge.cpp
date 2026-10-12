// Independent display-only translation bridge. No UObject or asset writes.
#include "CoreMinimal.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SWindow.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Text/SRichTextBlock.h"
#include "Widgets/Text/SInlineEditableTextBlock.h"
#include "Widgets/SToolTip.h"
#include "Widgets/SInvalidationPanel.h"
#include "Misc/ScopeExit.h"
#include "Stack/SNiagaraStackItemGroupAddMenu.h"
#include "NiagaraEditorUtilities.h"
#include "Widgets/SNiagaraParameterPanel.h"
#include "Framework/Application/SlateUser.h"
#include <set>
#include "SGraphActionMenu.h"
#include "EdGraph/EdGraph.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SSearchBox.h"
#include <map>
#include <string>
#include <vector>
#include <cwctype>

// C++ explicit instantiation permits naming a private member here. Keep this
// accessor isolated; engine fingerprints are checked before loading this DLL.
// ToAttribute preserves the original live getter, unlike copying GetText().
struct FTextAttributeType : STextBlock { using AttributeType = SWidget::TSlateAttribute<FText>; };
struct FTextAttributeTag {
    using Type = FTextAttributeType::AttributeType STextBlock::*;
    friend Type TextAttribute(FTextAttributeTag);
};
template<class Tag, typename Tag::Type Member> struct TMemberAccess {
    friend typename Tag::Type TextAttribute(Tag) { return Member; }
};
template struct TMemberAccess<FTextAttributeTag, &STextBlock::BoundText>;
struct FEnterTag {
    using Type = FSimpleDelegate SInlineEditableTextBlock::*;
    friend Type TextAttribute(FEnterTag);
};
template struct TMemberAccess<FEnterTag, &SInlineEditableTextBlock::OnEnterEditingMode>;
struct FSelectorTag {
    using Type = TSharedPtr<SNiagaraStackAddSelector> SNiagaraStackItemGroupAddMenu::*;
    friend Type TextAttribute(FSelectorTag);
};
template struct TMemberAccess<FSelectorTag, &SNiagaraStackItemGroupAddMenu::ActionSelector>;
struct FItemsTag {
    using Type = TArray<TSharedPtr<FNiagaraMenuAction_Generic>> SNiagaraStackAddSelector::*;
    friend Type TextAttribute(FItemsTag);
};
template struct TMemberAccess<FItemsTag, &SNiagaraStackAddSelector::Items>;
struct FRichTextTag {
    using Type = TAttribute<FText> SRichTextBlock::*;
    friend Type TextAttribute(FRichTextTag);
};
template struct TMemberAccess<FRichTextTag, &SRichTextBlock::BoundText>;

struct FGraphListTag {
    using Type=TSharedPtr<FGraphActionListBuilderBase> SGraphActionMenu::*;
    friend Type TextAttribute(FGraphListTag);
};
template struct TMemberAccess<FGraphListTag,&SGraphActionMenu::AllActions>;
struct FTooltipWindowTag {
    using Type=TWeakPtr<SWindow> FSlateUser::*;
    friend Type TextAttribute(FTooltipWindowTag);
};
template struct TMemberAccess<FTooltipWindowTag,&FSlateUser::TooltipWindowPtr>;
struct FParameterSelectorTag {
    using Type=TSharedPtr<SNiagaraParameterPanelSelector> SNiagaraParameterPanel::*;
    friend Type TextAttribute(FParameterSelectorTag);
};
template struct TMemberAccess<FParameterSelectorTag,&SNiagaraParameterPanel::ItemSelector>;
// Explicit-instantiation access, constrained by matching engine fingerprints.
using FParameterFilter=SNiagaraParameterPanelSelector::FOnDoesItemMatchFilterText;
FParameterFilter* ParameterFilter(SNiagaraParameterPanelSelector&);
void* ParameterModelIdentity(SNiagaraParameterPanelSelector&);
bool ParameterPasses(SNiagaraParameterPanelSelector&,const FNiagaraParameterPanelItem&);
template<class Model,auto ModelMember,auto FilterMember> struct TParameterModelAccess {
    friend FParameterFilter* ParameterFilter(SNiagaraParameterPanelSelector& S){
        auto M=S.*ModelMember;return M?&(M.Get()->*FilterMember):nullptr;
    }
    friend void* ParameterModelIdentity(SNiagaraParameterPanelSelector& S){return (S.*ModelMember).Get();}
    friend bool ParameterPasses(SNiagaraParameterPanelSelector& S,const FNiagaraParameterPanelItem& I){return (S.*ModelMember)->DoesItemPassFilter(I);}
};
template struct TParameterModelAccess<SNiagaraParameterPanelSelector::FItemSelectorViewModel,
    &SNiagaraParameterPanelSelector::ViewModelUtilities,
    &SNiagaraParameterPanelSelector::FItemSelectorViewModel::OnDoesItemMatchFilterText>;
struct FParameterItemsTag {
    using Type=TArray<FNiagaraParameterPanelItem> SNiagaraParameterPanelSelector::*;
    friend Type TextAttribute(FParameterItemsTag);
};
template struct TMemberAccess<FParameterItemsTag,&SNiagaraParameterPanelSelector::Items>;
static bool Collecting=false;
static std::vector<std::wstring> PendingCapture;
static std::set<std::wstring> PendingKeys;
static double LastScanMs=0;
static std::map<std::wstring,std::wstring> GraphDictionary;
static std::map<std::wstring, std::wstring> Dictionary;
static std::map<std::wstring, std::wstring> NormalizedDictionary;
struct FTrieNode { std::map<wchar_t,size_t> Next; std::wstring Translation; };
static std::vector<FTrieNode> PhraseTrie(1);
static std::map<std::wstring, bool> Observed;
static std::vector<std::wstring> Current;
static std::map<std::wstring,std::wstring> LookupCache;
static FDelegateHandle PreTickHandle;
static double LastScan=0;
static double WarmUntil=0;
static bool Enabled = false;
static bool Bilingual = false;
static uint64 Revision = 0;
struct FBinding {
    TWeakPtr<STextBlock> Widget;
    TAttribute<FText> Original;
    FDelegateHandle Handle;
    FString LastSource;
    FText LastResult;
    uint64 LastRevision = ~uint64(0);
    bool Overview = false;
    bool Graph = false;
    bool Tooltip = false;
};
static TMap<STextBlock*, TSharedPtr<FBinding>> Bindings;
struct FRichBinding : FBinding { TWeakPtr<SRichTextBlock> RichWidget; };
static TMap<SRichTextBlock*, TSharedPtr<FRichBinding>> RichBindings;
struct FEditGuard {
    TWeakPtr<SInlineEditableTextBlock> Widget;
    FSimpleDelegate Original;
    FDelegateHandle Handle;
};
static TMap<SInlineEditableTextBlock*, TSharedPtr<FEditGuard>> EditGuards;
struct FSearchBinding {
    TWeakPtr<FNiagaraMenuAction_Generic> Action;
    FText Keywords, AppliedKeywords;
    TOptional<FText> Alternate, AppliedAlternate;
    FString FullSearch, AppliedFullSearch, Name, Categories;
    uint64 AppliedRevision = ~uint64(0);
};
static TMap<FNiagaraMenuAction_Generic*, FSearchBinding> SearchBindings;
static TMap<SNiagaraStackAddSelector*, TWeakPtr<SNiagaraStackAddSelector>> SearchSelectors;

static bool Space(wchar_t C) { return iswspace(C) || C==0xA0 || C==0x3000; }
static bool Word(wchar_t C) { return iswalnum(C) || C==L'_'; }
struct FNormalized {
    std::wstring Text;
    std::vector<size_t> Begin, End;
};
static FNormalized Normalize(const std::wstring& Source) {
    FNormalized Result;
    for (size_t I=0; I<Source.size(); ++I) {
        wchar_t C=Source[I];
        if (Space(C)) {
            if (Result.Text.empty()) continue;
            if (Result.Text.back()==L' ') { Result.End.back()=I+1; continue; }
            C=L' ';
        } else if (C==0xFF1A) C=L':';
        Result.Text.push_back(towlower(C));Result.Begin.push_back(I);Result.End.push_back(I+1);
    }
    if (!Result.Text.empty() && Result.Text.back()==L' ') {
        Result.Text.pop_back();Result.Begin.pop_back();Result.End.pop_back();
    }
    return Result;
}
#include "LabelAliases.inl"
static bool HasUntranslatedWord(const std::wstring& Source, size_t Begin, size_t End) {
    // Keep named placeholders intact, but never publish a partially translated
    // sentence/label just because a few personal dictionary phrases matched.
    for (size_t I=Begin; I<End; ++I) {
        if (Source[I]==L'{') {
            auto Close=Source.find(L'}',I+1);
            if (Close!=std::wstring::npos && Close<End) { I=Close;continue; }
        }
        if ((Source[I]>=L'A' && Source[I]<=L'Z') || (Source[I]>=L'a' && Source[I]<=L'z')) return true;
    }
    return false;
}
static std::wstring LookupUncached(const std::wstring& Source) {
    auto Exact=Dictionary.find(Source);
    if (Exact!=Dictionary.end()) return Exact->second;
    auto Normal=Normalize(Source);
    auto Canonical=NormalizedDictionary.find(Normal.Text);
    if (Canonical!=NormalizedDictionary.end()) return Canonical->second;
    std::wstring Alias;
    if(LookupLabelAlias(Source,Alias))return Alias;
    // Numbered compact parameter labels share a base translation. Exact entries
    // above still win; preserve the index and leave dimension/type names alone.
    size_t Digit=Source.size();
    while(Digit>0 && Source[Digit-1]>=L'0' && Source[Digit-1]<=L'9') --Digit;
    if(Digit>0 && Digit<Source.size()) {
        bool Letters=true,Camel=false;
        for(size_t I=0;I<Digit;++I) {
            wchar_t C=Source[I];
            if(!((C>=L'A' && C<=L'Z') || (C>=L'a' && C<=L'z'))) { Letters=false;break; }
            if(I>0 && Source[I-1]>=L'a' && Source[I-1]<=L'z' && C>=L'A' && C<=L'Z')Camel=true;
        }
        if(Letters && Camel) {
            auto Stem=Source.substr(0,Digit);
            auto Base=NormalizedDictionary.find(Normalize(Stem).Text);
            if(Base!=NormalizedDictionary.end())return Base->second+L" "+Source.substr(Digit);
            if(LookupLabelAlias(Stem,Alias))return Alias+L" "+Source.substr(Digit);
        }
    }
    std::wstring Result;
    size_t Copied=0;
    for (size_t I=0; I<Normal.Text.size();) {
        if (Normal.Text[I]==L'{') {
            auto End=Normal.Text.find(L'}',I+1);
            if (End!=std::wstring::npos) { I=End+1; continue; }
        }
        if (I>0 && Word(Normal.Text[I-1]) && Word(Normal.Text[I])) { ++I;continue; }
        size_t Node=0, BestEnd=I;const std::wstring* Best=nullptr;
        for (size_t J=I; J<Normal.Text.size(); ++J) {
            auto It=PhraseTrie[Node].Next.find(Normal.Text[J]);
            if (It==PhraseTrie[Node].Next.end())break;
            Node=It->second;
            if (!PhraseTrie[Node].Translation.empty() &&
                (J+1==Normal.Text.size() || !Word(Normal.Text[J]) || !Word(Normal.Text[J+1]))) {
                Best=&PhraseTrie[Node].Translation;BestEnd=J+1;
            }
        }
        if (Best) {
            if (HasUntranslatedWord(Source,Copied,Normal.Begin[I])) return Source;
            Result.append(Source,Copied,Normal.Begin[I]-Copied);Result+=*Best;
            Copied=Normal.End[BestEnd-1];I=BestEnd;
        } else ++I;
    }
    if (Copied==0)return Source;
    if (HasUntranslatedWord(Source,Copied,Source.size())) return Source;
    Result.append(Source,Copied,std::wstring::npos);return Result;
}
static std::wstring Lookup(const std::wstring& Source) {
    auto It=LookupCache.find(Source);
    if(It!=LookupCache.end())return It->second;
    auto Value=LookupUncached(Source);
    if(LookupCache.size()<20000)LookupCache.emplace(Source,Value);
    return Value;
}

#include "SearchAliases.inl"
#include "ParameterSearch.inl"

static std::wstring GraphLookup(const std::wstring& Source) {
    auto It=GraphDictionary.find(Normalize(Source).Text);
    if(It!=GraphDictionary.end())return It->second;
    return Lookup(Source);
}
static void CaptureSource(const FString& Source,bool Graph=false) {
    if(!Collecting || Source.Len()<2 || Source.Len()>32000)return;
    bool English=false;
    for(TCHAR C:Source)if((C>=L'A' && C<=L'Z') || (C>=L'a' && C<=L'z')){English=true;break;}
    if(!English)return;
    const std::wstring Key(*Source);
    if((Graph?GraphLookup(Key):Lookup(Key))!=Key)return;
    if(Observed.size()<20000)Observed[Key]=true;
    // Keep short-lived popup/tooltip text until Python has safely written it.
    if(PendingCapture.size()<20000 && PendingKeys.insert(Key).second)PendingCapture.push_back(Key);
}
static bool HasChinese(const FString& Value) {
    for(TCHAR C:Value)if(C>=0x3400 && C<=0x9fff)return true;
    return false;
}
#include "TooltipText.inl"

// Graph menu aliases live only in transient action search caches. Node names,
// categories, context filters and activation delegates remain engine-owned.
struct FGraphCache {
    TArray<FString> Titles, Categories;
    FString Search;
    void Read(const FEdGraphSchemaAction& A) {
        Titles=A.LocalizedFullSearchTitlesArray;Categories=A.LocalizedFullSearchCategoryArray;Search=A.SearchText;
    }
    bool Same(const FEdGraphSchemaAction& A) const {
        return Search==A.SearchText && Titles==A.LocalizedFullSearchTitlesArray && Categories==A.LocalizedFullSearchCategoryArray;
    }
    void RestoreOwned(FEdGraphSchemaAction& A,const FGraphCache& Applied) const {
        if(A.SearchText==Applied.Search)A.SearchText=Search;
        if(A.LocalizedFullSearchTitlesArray==Applied.Titles)A.LocalizedFullSearchTitlesArray=Titles;
        if(A.LocalizedFullSearchCategoryArray==Applied.Categories)A.LocalizedFullSearchCategoryArray=Categories;
    }
};
struct FGraphBinding {
    TWeakPtr<FEdGraphSchemaAction> Action;
    FGraphCache Original,Applied;
    FString Name,Category;
    uint64 AppliedRevision=~uint64(0);
};
struct FGraphMenuBinding {
    TWeakPtr<SGraphActionMenu> Menu;
    TWeakPtr<FGraphActionListBuilderBase> List;
    uint64 AppliedRevision=~uint64(0);
    int32 Cursor=0,Count=-1;
    double NextScan=0;
};
static TMap<FEdGraphSchemaAction*,FGraphBinding> GraphBindings;
static TMap<SGraphActionMenu*,FGraphMenuBinding> GraphMenus;
static void RestoreGraphAction(FGraphBinding& B) {
    if(auto A=B.Action.Pin())B.Original.RestoreOwned(*A,B.Applied);
}
static bool IndexGraphAction(const TSharedPtr<FEdGraphSchemaAction>& A) {
    if(!A || !Enabled)return false;
    auto* Existing=GraphBindings.Find(A.Get());
    if(Existing && Existing->Action.Pin()!=A){GraphBindings.Remove(A.Get());Existing=nullptr;}
    const FString Name=A->GetMenuDescription().ToString(),Category=A->GetCategory().ToString();
    if(Existing && Existing->AppliedRevision==Revision && Existing->Name==Name && Existing->Category==Category && Existing->Applied.Same(*A))return false;
    if(Existing)RestoreGraphAction(*Existing);
    FGraphBinding B;B.Action=A;B.Name=Name;B.Category=Category;B.AppliedRevision=Revision;B.Original.Read(*A);
    auto Add=[&](const FString& Source,TArray<FString>& Target){
        CaptureSource(Source,true);
        // Keep the engine's English/source form searchable, including compact names.
        FString English=Source.ToLower();
        Target.AddUnique(English);Target.AddUnique(English.Replace(TEXT(" "),TEXT("")));
        FString Value(GraphLookup(std::wstring(*Source)).c_str());
        for(const auto& Alias:SearchAliases(Source))if(HasChinese(Alias))Target.AddUnique(Alias.ToLower());
        for(const auto& Alias:SearchAliases(Value))if(HasChinese(Alias))Target.AddUnique(Alias.ToLower());
    };
    CaptureSource(A->GetTooltipDescription().ToString(),true);
    Add(Name,A->LocalizedFullSearchTitlesArray);
    Add(A->GetMenuDescription().BuildSourceString(),A->LocalizedFullSearchTitlesArray);
    TArray<FString> Categories;Category.ParseIntoArray(Categories,TEXT("|"),true);
    for(const auto& C:Categories)Add(C.TrimStartAndEnd(),A->LocalizedFullSearchCategoryArray);
    A->SearchText+=TEXT("\n")+FString::Join(A->LocalizedFullSearchTitlesArray,TEXT("\n"))+TEXT("\n")+FString::Join(A->LocalizedFullSearchCategoryArray,TEXT("\n"));
    B.Applied.Read(*A);const bool Changed=!B.Original.Same(*A);
    GraphBindings.Add(A.Get(),MoveTemp(B));return Changed;
}
static void IndexGraphMenu(const TSharedRef<SGraphActionMenu>& Menu) {
    if(!Enabled)return;
    const auto List=Menu.Get().*TextAttribute(FGraphListTag{});if(!List)return;
    auto& B=GraphMenus.FindOrAdd(&Menu.Get());
    if(B.Menu.Pin()!=Menu || B.List.Pin()!=List || B.Count!=List->GetNumActions() || B.AppliedRevision!=Revision){
        B=FGraphMenuBinding();B.Menu=Menu;B.List=List;B.Count=List->GetNumActions();B.AppliedRevision=Revision;
    }
    const double Now=FPlatformTime::Seconds();if(Now<B.NextScan)return;
    bool Changed=false;int32 Work=0;
    while(B.Cursor<B.Count && Work++<512){
        Changed|=IndexGraphAction(List->GetSchemaAction(B.Cursor++));
        if(FPlatformTime::Seconds()-Now>0.003)break;
    }
    if(B.Cursor>=B.Count){B.Cursor=0;B.NextScan=Now+0.25;}
    // GenerateFilteredItems does not execute actions (the engine guards selection).
    if(Changed && !Menu->GetFilterTextBox()->GetText().IsEmpty())Menu->GenerateFilteredItems(true);
}

static void RestoreSearchBinding(FSearchBinding& B) {
    if(auto A=B.Action.Pin()) {
        // Do not overwrite changes made by the owner after our last update.
        if(A->Keywords.IdenticalTo(B.AppliedKeywords))A->Keywords=B.Keywords;
        if(A->AlternateSearchName.IsSet() && B.AppliedAlternate.IsSet() &&
           A->AlternateSearchName->IdenticalTo(*B.AppliedAlternate))A->AlternateSearchName=B.Alternate;
        if(A->FullSearchString==B.AppliedFullSearch)A->FullSearchString=B.FullSearch;
    }
}
static bool IndexAction(const TSharedPtr<FNiagaraMenuAction_Generic>& A) {
    if(!A)return false;
    if(!Enabled){CaptureSource(A->DisplayName.ToString());CaptureSource(A->ToolTip.ToString());return false;}
    auto* Existing=SearchBindings.Find(A.Get());
    if(Existing && Existing->Action.Pin()!=A) { SearchBindings.Remove(A.Get());Existing=nullptr; }
    const FString Name=A->DisplayName.ToString(), Categories=FString::Join(A->Categories,TEXT("|"));
    if(Existing && Existing->AppliedRevision==Revision && Existing->Name==Name && Existing->Categories==Categories &&
       A->Keywords.IdenticalTo(Existing->AppliedKeywords))return false;
    CaptureSource(A->DisplayName.ToString());
    for(const auto& C:A->Categories)CaptureSource(C);
    CaptureSource(A->ToolTip.ToString());
    if(Existing)RestoreSearchBinding(*Existing);
    FSearchBinding B;
    B.Action=A;B.Keywords=A->Keywords;B.Alternate=A->AlternateSearchName;B.FullSearch=A->FullSearchString;
    B.Name=Name;B.Categories=Categories;B.AppliedRevision=Revision;
    TArray<FString> Aliases;
    auto AddAlias=[&Aliases](const FString& Source) {
        const FString Translated(Lookup(std::wstring(*Source)).c_str());
        if(HasChinese(Translated)) for(const auto& Alias:SearchAliases(Translated)) {
            Aliases.AddUnique(Alias);
            // Niagara's weight function requires StartsWith even after the filter
            // accepted Contains. Chinese has no spaces: suffix aliases let a user
            // find 添加速度 with 速度 without changing the engine's search delegates.
            for(int32 I=1;I<Alias.Len() && I<128;++I)
                if(Alias[I]>=0x3400 && Alias[I]<=0x9fff)Aliases.AddUnique(Alias.Mid(I));
        }
    };
    AddAlias(Name);
    for(const auto& C:A->Categories)AddAlias(C);
    if(Aliases.Num()) {
        A->Keywords=FText::FromString(B.Keywords.ToString()+TEXT(" ")+FString::Join(Aliases,TEXT(" ")));
        const FString TranslatedName(Lookup(std::wstring(*Name)).c_str());
        if(TranslatedName!=Name)A->AlternateSearchName=FText::FromString(
            (B.Alternate.IsSet()?B.Alternate->ToString()+TEXT(" "):FString())+TranslatedName);
        A->UpdateFullSearchText();
    }
    B.AppliedKeywords=A->Keywords;B.AppliedAlternate=A->AlternateSearchName;B.AppliedFullSearch=A->FullSearchString;
    SearchBindings.Add(A.Get(),MoveTemp(B));
    return true;
}
static void IndexMenu(const TSharedRef<SNiagaraStackItemGroupAddMenu>& Menu) {
    auto Selector=Menu.Get().*TextAttribute(FSelectorTag{});
    if(!Selector)return;
    SearchSelectors.Add(Selector.Get(),Selector);
    bool Changed=false;
    for(const auto& A:Selector.Get()->*TextAttribute(FItemsTag{}))Changed=IndexAction(A)||Changed;
    if(Changed)Selector->RefreshAllCurrentItems();
}

static FText Translate(FBinding& Binding) {
    FText Text = Binding.Original.Get();
    const FString& Source = Text.ToString();
    if (Binding.LastRevision == Revision && Binding.LastSource == Source) return Binding.LastResult;
    Binding.LastSource = Source;
    Binding.LastRevision = Revision;
    auto ValueString = DisplayText(Text, Binding.Graph, Binding.Tooltip);
    if (!Enabled || ValueString == std::wstring(*Source)) Binding.LastResult = Text;
    else {
        FString Value(ValueString.c_str());
        if (Bilingual) Value += TEXT(" (") + Source + TEXT(")");
        Binding.LastResult = FText::FromString(Value);
    }
    return Binding.LastResult;
}

static auto& Attribute(STextBlock& Widget) { return Widget.*TextAttribute(FTextAttributeTag{}); }
static bool Owns(STextBlock& Widget, const FBinding& Binding) {
    auto Current = Attribute(Widget).ToAttribute(Widget);
    return Current.IsBound() && Current.GetBinding().GetHandle() == Binding.Handle;
}
static bool OwnsRich(SRichTextBlock& Widget,const FRichBinding& Binding) {
    const auto& Attr=Widget.*TextAttribute(FRichTextTag{});
    return Attr.IsBound() && Attr.GetBinding().GetHandle()==Binding.Handle;
}
static void VisitRichText(const TSharedRef<SRichTextBlock>& Widget,bool Graph=false,bool Tooltip=false) {
    auto Existing=RichBindings.Find(&Widget.Get());
    const FText Text=Existing?(*Existing)->Original.Get():Widget->GetText();
    const FString Source=Text.ToString();
    const auto Value=DisplayText(Text,Graph,Tooltip,true);
    // Preserve rich-text decorators; translate complete plain labels in any panel.
    if(!Existing && Enabled && !Source.Contains(TEXT("<")) && Value!=std::wstring(*Source)) {
        auto B=MakeShared<FRichBinding>();B->RichWidget=Widget;B->Graph=Graph;B->Tooltip=Tooltip;
        B->Original=Widget.Get().*TextAttribute(FRichTextTag{});
        auto Getter=TAttribute<FText>::FGetter::CreateLambda([B](){return Translate(*B);});
        B->Handle=Getter.GetHandle();Widget->SetText(TAttribute<FText>::Create(Getter));
        RichBindings.Add(&Widget.Get(),B);
    }
}
static void RestoreChildren(const TSharedRef<SWidget>& Widget) {
    if (Widget->GetTypeAsString() == TEXT("STextBlock")) {
        auto TextWidget = StaticCastSharedRef<STextBlock>(Widget);
        if (auto Binding = Bindings.Find(&TextWidget.Get())) {
            if (Owns(TextWidget.Get(), **Binding)) TextWidget->SetText((*Binding)->Original);
            Bindings.Remove(&TextWidget.Get());
        }
    }
    auto Children = Widget->GetAllChildren();
    if (Children) for (int32 I=0; I<Children->Num(); ++I) RestoreChildren(Children->GetChildAt(I));
}
static bool OwnsGuard(SInlineEditableTextBlock& Widget, const FEditGuard& Guard) {
    return (Widget.*TextAttribute(FEnterTag{})).GetHandle() == Guard.Handle;
}
static void GuardEditing(const TSharedRef<SInlineEditableTextBlock>& Widget) {
    if (EditGuards.Contains(&Widget.Get())) return;
    auto Guard = MakeShared<FEditGuard>();
    Guard->Widget = Widget;
    Guard->Original = Widget.Get().*TextAttribute(FEnterTag{});
    auto Enter = FSimpleDelegate::CreateLambda([Guard]() {
        if (auto Owner=Guard->Widget.Pin()) RestoreChildren(Owner.ToSharedRef());
        Guard->Original.ExecuteIfBound();
    });
    Guard->Handle = Enter.GetHandle();
    Widget->SetOnEnterEditingMode(Enter);
    EditGuards.Add(&Widget.Get(), Guard);
}
static void Restore() {
    RestoreParameterSearch();
    for(auto& Pair:GraphBindings)RestoreGraphAction(Pair.Value);
    GraphBindings.Empty();
    for(auto& Pair:GraphMenus)if(auto Menu=Pair.Value.Menu.Pin())
        if(!Menu->GetFilterTextBox()->GetText().IsEmpty())Menu->GenerateFilteredItems(true);
    GraphMenus.Empty();
    for(auto& Pair:RichBindings)if(auto Widget=Pair.Value->RichWidget.Pin())
        if(OwnsRich(*Widget,*Pair.Value))Widget->SetText(Pair.Value->Original);
    RichBindings.Empty();
    for(auto& Pair:SearchBindings)RestoreSearchBinding(Pair.Value);
    SearchBindings.Empty();
    for(auto& Pair:SearchSelectors)if(auto Selector=Pair.Value.Pin())Selector->RefreshAllCurrentItems();
    SearchSelectors.Empty();
    for (auto& Item : Bindings) {
        auto Widget = Item.Value->Widget.Pin();
        if (Widget.IsValid() && Owns(*Widget, *Item.Value)) Widget->SetText(Item.Value->Original);
    }
    Bindings.Empty();
    for (auto& Item : EditGuards) {
        auto Widget=Item.Value->Widget.Pin();
        if (Widget.IsValid() && OwnsGuard(*Widget,*Item.Value)) Widget->SetOnEnterEditingMode(Item.Value->Original);
    }
    EditGuards.Empty();
}
static void VisitWidget(const TSharedRef<SWidget>& Widget, int Depth = 0, bool Overview = false, bool NiagaraMenu = false, bool GraphMenu = false, bool Tooltip = false) {
    if (Depth > 100 || !Widget->GetVisibility().IsVisible()) return;
    const FString Type = Widget->GetTypeAsString();
    Tooltip=Tooltip || Type==TEXT("SToolTip");
    if(Type==TEXT("SNiagaraParameterPanel")) {
        auto Panel=StaticCastSharedRef<SNiagaraParameterPanel>(Widget);
        if(auto Selector=Panel.Get().*TextAttribute(FParameterSelectorTag{}))IndexParameterSelector(Selector.ToSharedRef());
    }
    GraphMenu=GraphMenu || Type==TEXT("SGraphActionMenu");
    if(Type==TEXT("SGraphActionMenu"))IndexGraphMenu(StaticCastSharedRef<SGraphActionMenu>(Widget));
    NiagaraMenu=NiagaraMenu || Type==TEXT("SNiagaraStackItemGroupAddMenu");
    if(Type==TEXT("SNiagaraStackItemGroupAddMenu"))IndexMenu(StaticCastSharedRef<SNiagaraStackItemGroupAddMenu>(Widget));
    if(Type==TEXT("SRichTextBlock"))VisitRichText(StaticCastSharedRef<SRichTextBlock>(Widget),GraphMenu,Tooltip);
    Overview = Overview || Type.Contains(TEXT("NiagaraOverview")) || Type.Contains(TEXT("NiagaraSystemOverview"));
    if (Type.Contains(TEXT("EditableText")) && !Type.Contains(TEXT("InlineEditableText"))) return;
    if (Type.Contains(TEXT("InlineEditableText")) && Type != TEXT("SInlineEditableTextBlock")) return;
    if (Enabled && Type == TEXT("SInlineEditableTextBlock")) GuardEditing(StaticCastSharedRef<SInlineEditableTextBlock>(Widget));
    if (Type == TEXT("STextBlock")) {
        auto TextWidget = StaticCastSharedRef<STextBlock>(Widget);
        const auto Existing=Bindings.Find(&TextWidget.Get());
        const FText Text=Existing ? (*Existing)->Original.Get() : TextWidget->GetText();
        const FString Source=Text.ToString();
        const auto Value=DisplayText(Text,GraphMenu,Tooltip,true);
        if (!Bindings.Contains(&TextWidget.Get())) {
            if (Enabled && Value != std::wstring(*Source)) {
                auto Binding = MakeShared<FBinding>();
                Binding->Widget = TextWidget;
                Binding->Overview = Overview;Binding->Graph=GraphMenu;Binding->Tooltip=Tooltip;
                Binding->Original = Attribute(TextWidget.Get()).ToAttribute(TextWidget.Get());
                auto Getter = TAttribute<FText>::FGetter::CreateLambda([Binding]() { return Translate(*Binding); });
                Binding->Handle = Getter.GetHandle();
                TextWidget->SetText(TAttribute<FText>::Create(Getter));
                Bindings.Add(&TextWidget.Get(), Binding);
            }
        }
    }
    // Cached Niagara overview cards intentionally expose no ordinary children.
    // GetAllChildren preserves their cache and exposes the owned widget tree.
    FChildren* Children = Widget->GetAllChildren();
    if (Children) for (int32 I=0; I<Children->Num(); ++I) VisitWidget(Children->GetChildAt(I), Depth+1, Overview, NiagaraMenu, GraphMenu, Tooltip);
}

#define XH_EXPORT extern "C" __declspec(dllexport)
XH_EXPORT void XH_Clear() { Restore(); GraphDictionary.clear(); Dictionary.clear(); LookupCache.clear(); NormalizedDictionary.clear();LabelAliases.clear();PhraseTrie.clear();PhraseTrie.emplace_back(); ++Revision; }
XH_EXPORT void XH_Add(const wchar_t* Source, const wchar_t* Translation) {
    Dictionary[Source] = Translation;NormalizedDictionary[Normalize(Source).Text]=Translation;LookupCache.clear(); ++Revision;
    AddLabelAlias(Source,Translation);
}
XH_EXPORT void XH_AddGraph(const wchar_t* Source,const wchar_t* Translation) {
    GraphDictionary[Normalize(Source).Text]=Translation;++Revision;
}
XH_EXPORT void XH_AddLegacy(const wchar_t* Source, const wchar_t* Translation) {
    auto Key=Normalize(Source).Text;
    if (Key.size()<4 || Key.find_first_of(L"{}%")!=std::wstring::npos)return;
    size_t Node=0;
    for (wchar_t C:Key) {
        auto It=PhraseTrie[Node].Next.find(C);
        if (It==PhraseTrie[Node].Next.end()) {
            size_t Next=PhraseTrie.size();PhraseTrie[Node].Next[C]=Next;PhraseTrie.emplace_back();Node=Next;
        } else Node=It->second;
    }
    PhraseTrie[Node].Translation=Translation;LookupCache.clear();++Revision;
}
static std::wstring Preview;
XH_EXPORT const wchar_t* XH_Preview(const wchar_t* Source) { Preview=Lookup(Source);return Preview.c_str(); }
XH_EXPORT void XH_Collect(int Value){
    const bool NewValue=Value!=0;
    if(Collecting!=NewValue){Collecting=NewValue;++Revision;LastScan=0;}
}
XH_EXPORT int XH_IsCollecting(){return Collecting?1:0;}
XH_EXPORT double XH_ScanMs(){return LastScanMs;}
XH_EXPORT void XH_AckCapture(int Count){
    const size_t N=FMath::Clamp(Count,0,static_cast<int>(PendingCapture.size()));
    for(size_t I=0;I<N;++I)PendingKeys.erase(PendingCapture[I]);
    PendingCapture.erase(PendingCapture.begin(),PendingCapture.begin()+N);
}
XH_EXPORT int XH_CurrentCount() { return static_cast<int>(PendingCapture.size()); }
XH_EXPORT const wchar_t* XH_Current(int Index) { return Index>=0 && Index<static_cast<int>(PendingCapture.size()) ? PendingCapture[Index].c_str() : L""; }
XH_EXPORT void XH_Enable(int Enable, int Dual) {
    Enabled = Enable != 0; Bilingual = Dual != 0; ++Revision;
    if (!Enabled) Restore();
}
XH_EXPORT int XH_Tick() {
    if (!IsInGameThread() || !FSlateApplication::IsInitialized()) return -1;
    for(auto It=ParameterBindings.CreateIterator();It;++It)if(!It.Value()->Selector.IsValid())It.RemoveCurrent();
    for(auto It=GraphBindings.CreateIterator();It;++It)if(!It.Value().Action.IsValid())It.RemoveCurrent();
    for(auto It=GraphMenus.CreateIterator();It;++It)if(!It.Value().Menu.IsValid())It.RemoveCurrent();
    for(auto It=SearchBindings.CreateIterator();It;++It)if(!It.Value().Action.IsValid())It.RemoveCurrent();
    for(auto It=SearchSelectors.CreateIterator();It;++It)if(!It.Value().IsValid())It.RemoveCurrent();
    for(auto It=RichBindings.CreateIterator();It;++It) {
        auto Widget=It.Value()->RichWidget.Pin();
        if(!Widget || !OwnsRich(*Widget,*It.Value()))It.RemoveCurrent();
    }
    for (auto It=Bindings.CreateIterator(); It; ++It) {
        auto Widget=It.Value()->Widget.Pin();
        if (!Widget.IsValid() || !Owns(*Widget, *It.Value())) It.RemoveCurrent();
    }
    for (auto It=EditGuards.CreateIterator(); It; ++It) {
        auto Widget=It.Value()->Widget.Pin();
        if (!Widget.IsValid() || !OwnsGuard(*Widget,*It.Value())) It.RemoveCurrent();
    }
    const double ScanStart=FPlatformTime::Seconds();
    {
        TArray<TSharedRef<SWindow>> Windows;
        FSlateApplication::Get().GetAllVisibleWindowsOrdered(Windows);
        for (auto& Window : Windows) VisitWidget(Window);
        // Non-interactive tooltips are hosted separately and may be absent from
        // GetAllVisibleWindowsOrdered. Visit only active tooltip windows, never
        // call every widget's tooltip getter (which can start preview movies).
        FSlateApplication::Get().ForEachUser([&Windows](FSlateUser& User){
            if(auto Window=(User.*TextAttribute(FTooltipWindowTag{})).Pin())
                if(Window->IsVisible() && !Windows.Contains(Window.ToSharedRef()))VisitWidget(Window.ToSharedRef(),0,false,false,false,true);
        });
    }
    LastScanMs=(FPlatformTime::Seconds()-ScanStart)*1000.0;
    return Bindings.Num();
}
XH_EXPORT int XH_BindingCount() { return Bindings.Num()+RichBindings.Num(); }
XH_EXPORT void XH_Service(int Start) {
    if(!FSlateApplication::IsInitialized())return;
    if(PreTickHandle.IsValid()) {
        FSlateApplication::Get().OnPreTick().Remove(PreTickHandle);PreTickHandle.Reset();
    }
    if(Start) {
        WarmUntil=FPlatformTime::Seconds()+3.0;LastScan=0;
        PreTickHandle=FSlateApplication::Get().OnPreTick().AddLambda([](float) {
            double Now=FPlatformTime::Seconds();
            if(Now-LastScan>=(Collecting?0.10:0.25)) { LastScan=Now;XH_Tick(); }
        });
        XH_Tick();
    } else Restore();
}
XH_EXPORT int XH_BoundOverview(int Index) {
    int CurrentIndex=0;
    for(auto& Item:Bindings)if(Item.Value->Widget.IsValid() && CurrentIndex++==Index)return Item.Value->Overview?1:0;
    return 0;
}
XH_EXPORT int XH_ObservedCount() { return static_cast<int>(Observed.size()); }
XH_EXPORT const wchar_t* XH_Observed(int Index) {
    if (Index < 0 || Index >= static_cast<int>(Observed.size())) return L"";
    auto It = Observed.begin(); std::advance(It, Index); return It->first.c_str();
}
static FString Diagnostic;
XH_EXPORT int XH_ParameterPanelCount(){return ParameterBindings.Num();}
XH_EXPORT int XH_ParameterCount(){
    int N=0;for(auto& P:ParameterBindings)if(auto S=P.Value->Selector.Pin())N+=(S.Get()->*TextAttribute(FParameterItemsTag{})).Num();return N;
}
XH_EXPORT const wchar_t* XH_ParameterProbe(const wchar_t* Query){
    Diagnostic.Empty();TSet<FString> Seen;
    for(auto& P:ParameterBindings)if(auto S=P.Value->Selector.Pin())
        for(const auto& I:S.Get()->*TextAttribute(FParameterItemsTag{}))
            if(I.ScriptVariable && ParameterMatches(*P.Value,FText::FromString(Query),I)){
                const FString Name=I.GetVariable().GetName().ToString();
                if(!Seen.Contains(Name)){Seen.Add(Name);Diagnostic+=Name+TEXT("\n");}
            }
    return *Diagnostic;
}
XH_EXPORT int XH_ParameterSelfTest(){
    if(!IsInGameThread())return -1;
    XH_Clear();XH_Enable(1,0);XH_Collect(0);
    XH_Add(L"Particles",L"粒子");XH_Add(L"Sprite Size",L"精灵尺寸");
    XH_Add(L"Age",L"年龄");XH_Add(L"DynamicMaterialParameter",L"动态材质参数");
    auto MakeItem=[](const TCHAR* Name){
        auto* Variable=NewObject<UNiagaraScriptVariable>();
        Variable->Variable=FNiagaraVariable(FNiagaraTypeDefinition::GetFloatDef(),FName(Name));
        FNiagaraParameterPanelItem Item;Item.ScriptVariable=Variable;
        Item.NamespaceMetaData.DisplayName=FText::FromString(TEXT("粒子"));return Item;
    };
    const auto Sprite=MakeItem(TEXT("Particles.SpriteSize"));
    const auto Age=MakeItem(TEXT("Particles.Age"));
    const auto Numbered=MakeItem(TEXT("Particles.DynamicMaterialParameter2"));
    const auto Blocked=MakeItem(TEXT("Particles.Blocked"));
    TArray<FNiagaraParameterPanelItem> Items{Sprite,Age,Numbered,Blocked};
    auto Selector=SNew(SNiagaraParameterPanelSelector).Items(Items)
        .OnGenerateWidgetForItem_Lambda([](const FNiagaraParameterPanelItem& I)->TSharedRef<SWidget>{return SNew(STextBlock).Text(FText::FromName(I.GetVariable().GetName()));})
        .OnDoesItemMatchFilterText_Lambda([](const FText& Q,const FNiagaraParameterPanelItem& I){return I.GetVariable().GetName().ToString().Contains(Q.ToString());})
        .OnDoesItemPassCustomFilter_Lambda([](const FNiagaraParameterPanelItem& I){return !I.GetVariable().GetName().ToString().Contains(TEXT("Blocked"));});
    auto Search=StaticCastSharedRef<SSearchBox>(Selector->GetSearchBox());
    const auto OriginalHandle=ParameterFilter(Selector.Get())->GetHandle();
    Search->SetText(FText::FromString(TEXT("精灵尺寸")));
    if(ParameterPasses(Selector.Get(),Sprite))return 401;
    IndexParameterSelector(Selector);
    for(const TCHAR* Q:{TEXT("SpriteSize"),TEXT("spritesize"),TEXT("Sprite Size"),TEXT("精灵尺寸"),TEXT("Particles 尺寸"),TEXT("粒子精灵尺寸"),TEXT("大小"),TEXT("精灵大小"),TEXT("Particles 大小"),TEXT("粒子精灵大小")}){
        Search->SetText(FText::FromString(Q));
        if(!ParameterPasses(Selector.Get(),Sprite) || ParameterPasses(Selector.Get(),Age))return 402;
    }
    Search->SetText(FText::FromString(TEXT("动态材质参数 2")));
    if(!ParameterPasses(Selector.Get(),Numbered))return 403;
    Search->SetText(FText::FromString(TEXT("粒子")));
    if(ParameterPasses(Selector.Get(),Blocked))return 404;
    Search->SetText(FText::FromString(TEXT("用户尺寸")));
    if(ParameterPasses(Selector.Get(),Sprite))return 405;
    XH_Add(L"Sprite Size",L"用户尺寸");IndexParameterSelector(Selector);
    if(!ParameterPasses(Selector.Get(),Sprite))return 406;
    XH_Add(L"Sprite Size",L"用户大小");IndexParameterSelector(Selector);
    if(!ParameterPasses(Selector.Get(),Sprite))return 412;
    Search->SetText(FText::FromString(TEXT("精灵大小")));
    if(ParameterPasses(Selector.Get(),Sprite))return 413; // stale aliases must disappear
    const auto NewItem=MakeItem(TEXT("Particles.CustomValue"));
    Items.Add(NewItem);Selector->RefreshItems(Items);
    XH_Add(L"CustomValue",L"自定值");IndexParameterSelector(Selector);
    Search->SetText(FText::FromString(TEXT("自定值")));
    if(!ParameterPasses(Selector.Get(),NewItem))return 407;
    if(Sprite.GetVariable().GetName()!=FName(TEXT("Particles.SpriteSize")))return 408;
    XH_Enable(0,0);
    if(ParameterFilter(Selector.Get())->GetHandle()!=OriginalHandle || ParameterPasses(Selector.Get(),NewItem))return 409;
    Search->SetText(FText::FromString(TEXT("SpriteSize")));
    if(!ParameterPasses(Selector.Get(),Sprite))return 410;
    XH_Enable(1,0);IndexParameterSelector(Selector);
    auto External=FParameterFilter::CreateLambda([](const FText&,const FNiagaraParameterPanelItem&){return false;});
    *ParameterFilter(Selector.Get())=External;
    XH_Enable(0,0);
    if(ParameterFilter(Selector.Get())->GetHandle()!=External.GetHandle())return 411;
    XH_Clear();return 0;
}
XH_EXPORT const wchar_t* XH_GraphPreview(const wchar_t* Source){Preview=GraphLookup(Source);return Preview.c_str();}
XH_EXPORT int XH_GraphTranslatedCount(){int N=0;for(auto& P:GraphBindings)if(auto A=P.Value.Action.Pin()){auto S=A->GetMenuDescription().ToString();if(GraphLookup(*S)!=std::wstring(*S))++N;}return N;}
XH_EXPORT int XH_SearchTranslatedCount(){int N=0;for(auto& P:SearchBindings)if(auto A=P.Value.Action.Pin()){auto S=A->DisplayName.ToString();if(Lookup(*S)!=std::wstring(*S))++N;}return N;}
XH_EXPORT int XH_GraphCount(){return GraphBindings.Num();}
XH_EXPORT const wchar_t* XH_GraphName(int Index){
    int I=0;for(auto& Pair:GraphBindings)if(auto A=Pair.Value.Action.Pin())if(I++==Index){Diagnostic=A->GetMenuDescription().ToString();return *Diagnostic;}return L"";
}
XH_EXPORT const wchar_t* XH_GraphProbe(const wchar_t* Query){
    Diagnostic.Empty();TArray<FString> Terms;FString(Query).ToLower().ParseIntoArray(Terms,TEXT(" "),true);
    for(auto& Pair:GraphBindings)if(auto A=Pair.Value.Action.Pin()){
        bool Match=true;for(const auto& Term:Terms)if(!A->SearchText.Contains(Term,ESearchCase::CaseSensitive))Match=false;
        if(Match)Diagnostic+=A->GetMenuDescription().ToString()+TEXT("\n");
    }return *Diagnostic;
}
XH_EXPORT int XH_SearchCount() { return SearchBindings.Num(); }
XH_EXPORT const wchar_t* XH_SearchName(int Index) {
    int I=0;
    for(auto& Pair:SearchBindings)if(auto A=Pair.Value.Action.Pin())if(I++==Index) {
        Diagnostic=A->DisplayName.ToString();return *Diagnostic;
    }
    return L"";
}
XH_EXPORT const wchar_t* XH_SearchProbe(const wchar_t* Query) {
    Diagnostic.Empty();TArray<FString> Terms;
    FString(Query).ParseIntoArray(Terms,TEXT(" "),true);
    for(auto& Pair:SearchBindings)if(auto A=Pair.Value.Action.Pin()) {
        if(FNiagaraEditorUtilities::DoesItemMatchFilterText(FText::FromString(Query),A) &&
           FNiagaraEditorUtilities::GetWeightForItem(A,NAME_None,Terms)!=INDEX_NONE)
            Diagnostic+=A->DisplayName.ToString()+TEXT("\n");
    }
    return *Diagnostic;
}
XH_EXPORT int XH_GraphSelfTest() {
    if(!IsInGameThread())return -1;
    XH_Clear();XH_Enable(1,0);
    XH_AddGraph(L"Print String",L"打印字符串");XH_AddGraph(L"Development",L"开发");
    auto A=MakeShared<FEdGraphSchemaAction>(FText::FromString(TEXT("Utilities|Development")),FText::FromString(TEXT("Print String")),FText::FromString(TEXT("Original tooltip")),0,FText::FromString(TEXT("log")));
    FGraphCache Original;Original.Read(*A);
    auto List=MakeShared<FGraphActionListBuilderBase>();List->AddAction(A);
    List->AddAction(MakeShared<FEdGraphSchemaAction>(FText(),FText::FromString(TEXT("Other Action")),FText(),0));
    for(const TCHAR* SchemaPath:{TEXT("/Script/BlueprintGraph.EdGraphSchema_K2"),TEXT("/Script/UnrealEd.MaterialGraphSchema")}){
        List->Empty();List->AddAction(A);
        List->AddAction(MakeShared<FEdGraphSchemaAction>(FText(),FText::FromString(TEXT("Other Action")),FText(),0));
        auto* SchemaClass=LoadObject<UClass>(nullptr,SchemaPath);if(!SchemaClass)return 201;
        auto* Graph=NewObject<UEdGraph>();Graph->Schema=SchemaClass;
        FString Filter;bool Executed=false;
        auto Menu=SNew(SGraphActionMenu).GraphObj(Graph)
            .OnGetActionList_Lambda([List](){return List;})
            .OnGetFilterText_Lambda([&Filter](){return FText::FromString(Filter);})
            .OnActionSelected_Lambda([&Executed](const TArray<TSharedPtr<FEdGraphSchemaAction>>&,ESelectInfo::Type){Executed=true;});
        IndexGraphMenu(Menu);
        for(const TCHAR* Query:{TEXT("print string"),TEXT("打印字符串"),TEXT("字符串"),TEXT("开发"),TEXT("print 字符串"),TEXT("printstring"),TEXT("log")}){
            Filter=Query;Menu->GenerateFilteredItems(false);
            TArray<TSharedPtr<FEdGraphSchemaAction>> Selected;Menu->GetSelectedActions(Selected);
            if(Selected.Num()!=1 || Selected[0]!=A)return 202;
        }
        Filter=TEXT("不存在的词");Menu->GenerateFilteredItems(false);
        TArray<TSharedPtr<FEdGraphSchemaAction>> Selected;Menu->GetSelectedActions(Selected);
        if(Selected.Num()!=0 || Executed)return 203;
        if(A->GetMenuDescription().ToString()!=TEXT("Print String") || A->GetCategory().ToString()!=TEXT("Utilities|Development") || A->GetTooltipDescription().ToString()!=TEXT("Original tooltip"))return 204;
        const FString Once=A->SearchText;IndexGraphAction(A);if(A->SearchText!=Once)return 205;
        XH_AddGraph(L"Print String",L"个人打印");IndexGraphMenu(Menu);
        if(!A->SearchText.Contains(TEXT("个人打印")) || A->SearchText.Contains(TEXT("打印字符串")))return 206;
        // New entries and same-size replacement are indexed without recollection.
        auto New=MakeShared<FEdGraphSchemaAction>(FText(),FText::FromString(TEXT("Print String")),FText(),0);
        List->AddAction(New);IndexGraphMenu(Menu);if(!New->SearchText.Contains(TEXT("个人打印")))return 207;
        auto Replacement=MakeShared<FEdGraphSchemaAction>(FText(),FText::FromString(TEXT("Print String")),FText(),0);
        List->GetSchemaAction(2)=Replacement;GraphMenus.FindChecked(&Menu.Get()).NextScan=0;IndexGraphMenu(Menu);
        if(!Replacement->SearchText.Contains(TEXT("个人打印")))return 208;
        XH_Enable(0,0);if(!Original.Same(*A))return 209;
        XH_Enable(1,0);XH_AddGraph(L"Print String",L"打印字符串");
    }
    IndexGraphAction(A);A->SearchText=TEXT("external change");XH_Enable(0,0);
    if(A->SearchText!=TEXT("external change"))return 210;
    XH_Enable(1,0);
    FString Source(TEXT("Print String"));auto Label=SNew(STextBlock).Text_Lambda([&Source](){return FText::FromString(Source);});
    VisitWidget(Label,0,false,false,true);if(Label->GetText().ToString()!=TEXT("打印字符串"))return 211;
    XH_Enable(0,0);if(Label->GetText().ToString()!=TEXT("Print String"))return 212;
    XH_Clear();return 0;
}

XH_EXPORT int XH_SearchSelfTest() {
    if(!IsInGameThread())return -1;
    XH_Clear();XH_Enable(1,0);
    XH_Add(L"Add Velocity",L"添加速度");XH_Add(L"Location",L"位置");
    FString RichSource(TEXT("Location"));
    auto Rich=SNew(SRichTextBlock).Text_Lambda([&RichSource](){return FText::FromString(RichSource);});
    VisitWidget(Rich,0,false,true);
    if(Rich->GetText().ToString()!=TEXT("位置"))return 109;
    RichSource=TEXT("Add Velocity");
    if(Rich->GetText().ToString()!=TEXT("添加速度"))return 110;
    bool Executed=false;
    auto A=MakeShared<FNiagaraMenuAction_Generic>(
        FNiagaraMenuAction_Base::FOnExecuteAction::CreateLambda([&Executed](){Executed=true;}),
        FText::FromString(TEXT("Add Velocity")),TArray<FString>{TEXT("Location")},
        TOptional<FNiagaraFavoritesActionData>(),FText::FromString(TEXT("Original tooltip")),FText::FromString(TEXT("motion")));
    A->AlternateSearchName=FText::FromString(TEXT("OriginalAlias"));A->UpdateFullSearchText();
    const FString OriginalFull=A->FullSearchString;
    IndexAction(A);
    for(const wchar_t* Query:{L"Add Velocity",L"添加速度",L"速度",L"位置",L"motion",L"Add 速度"}) {
        if(!FString(XH_SearchProbe(Query)).Contains(TEXT("Add Velocity")))return 101;
    }
    if(A->DisplayName.ToString()!=TEXT("Add Velocity") || A->Categories[0]!=TEXT("Location") ||
       A->ToolTip.ToString()!=TEXT("Original tooltip"))return 102;
    A->Execute();if(!Executed)return 103;
    const FString Applied=A->Keywords.ToString();IndexAction(A);
    if(A->Keywords.ToString()!=Applied)return 104;
    XH_Add(L"Add Velocity",L"个人速度别名");IndexAction(A);
    if(!FString(XH_SearchProbe(L"个人速度")).Contains(TEXT("Add Velocity")))return 105;
    if(A->Keywords.ToString().Contains(TEXT("添加速度")))return 106;
    XH_Enable(0,0);
    if(Rich->GetText().ToString()!=TEXT("Add Velocity"))return 111;
    if(A->Keywords.ToString()!=TEXT("motion") || A->AlternateSearchName->ToString()!=TEXT("OriginalAlias") ||
       A->FullSearchString!=OriginalFull)return 107;
    XH_Enable(1,0);IndexAction(A);
    A->Keywords=FText::FromString(TEXT("external change"));XH_Enable(0,0);
    if(A->Keywords.ToString()!=TEXT("external change"))return 108;
    XH_Clear();return 0;
}
XH_EXPORT int XH_SynonymSelfTest() {
    if(!IsInGameThread())return -1;
    XH_Clear();XH_Enable(1,0);XH_Collect(0);
    if(!SearchAliases(TEXT("颜色尺寸")).Contains(TEXT("色彩大小")) ||
       !SearchAliases(TEXT("色彩大小")).Contains(TEXT("颜色尺寸")))return 501;
    if(SearchAliases(TEXT("不透明度")).Num()!=1)return 502;
    for(const TCHAR* Translation:{TEXT("精灵尺寸"),TEXT("精灵大小")}){
        XH_Add(L"Sprite Size",Translation);XH_AddGraph(L"Sprite Size",Translation);
        auto Niagara=MakeShared<FNiagaraMenuAction_Generic>(
            FNiagaraMenuAction_Base::FOnExecuteAction(),FText::FromString(TEXT("Sprite Size")),
            TArray<FString>(),TOptional<FNiagaraFavoritesActionData>(),FText(),FText());
        IndexAction(Niagara);
        for(const wchar_t* Query:{L"尺寸",L"大小",L"精灵大小",L"精灵尺寸",L"Sprite 大小"})
            if(!FString(XH_SearchProbe(Query)).Contains(TEXT("Sprite Size")))return 503;
        if(Niagara->DisplayName.ToString()!=TEXT("Sprite Size"))return 504;
        for(const TCHAR* SchemaPath:{TEXT("/Script/BlueprintGraph.EdGraphSchema_K2"),TEXT("/Script/UnrealEd.MaterialGraphSchema")}){
            auto A=MakeShared<FEdGraphSchemaAction>(FText(),FText::FromString(TEXT("Sprite Size")),FText(),0);
            FGraphCache Original;Original.Read(*A);
            auto List=MakeShared<FGraphActionListBuilderBase>();List->AddAction(A);
            List->AddAction(MakeShared<FEdGraphSchemaAction>(FText(),FText::FromString(TEXT("Age")),FText(),0));
            auto* Schema=LoadObject<UClass>(nullptr,SchemaPath);if(!Schema)return 505;
            auto* Graph=NewObject<UEdGraph>();Graph->Schema=Schema;
            FString Filter;bool Executed=false;
            auto Menu=SNew(SGraphActionMenu).GraphObj(Graph)
                .OnGetActionList_Lambda([List](){return List;})
                .OnGetFilterText_Lambda([&Filter](){return FText::FromString(Filter);})
                .OnActionSelected_Lambda([&Executed](const TArray<TSharedPtr<FEdGraphSchemaAction>>&,ESelectInfo::Type){Executed=true;});
            IndexGraphMenu(Menu);
            for(const TCHAR* Query:{TEXT("大小"),TEXT("尺寸"),TEXT("精灵大小"),TEXT("sprite 大小")}){
                Filter=Query;Menu->GenerateFilteredItems(false);
                TArray<TSharedPtr<FEdGraphSchemaAction>> Selected;Menu->GetSelectedActions(Selected);
                if(Selected.Num()!=1 || Selected[0]!=A || Executed)return 506;
            }
            XH_Enable(0,0);if(!Original.Same(*A))return 507;
            XH_Enable(1,0);
        }
    }
    XH_Clear();return 0;
}
XH_EXPORT const wchar_t* XH_BoundText(int Index, int Translated) {
    int Current = 0;
    for (auto& Item : Bindings) {
        auto Widget = Item.Value->Widget.Pin();
        if (Widget.IsValid() && Current++ == Index) {
            Diagnostic = Translated ? Widget->GetText().ToString() : Item.Value->Original.Get().ToString();
            return *Diagnostic;
        }
    }
    for(auto& Item:RichBindings) {
        auto Widget=Item.Value->RichWidget.Pin();
        if(Widget.IsValid() && Current++==Index) {
            Diagnostic=Translated?Widget->GetText().ToString():Item.Value->Original.Get().ToString();
            return *Diagnostic;
        }
    }
    return TEXT("");
}
XH_EXPORT int XH_CaptureSelfTest(){
    if(!IsInGameThread())return -1;
    XH_Clear();PendingCapture.clear();PendingKeys.clear();Observed.clear();XH_Collect(0);XH_Enable(1,0);
    XH_Add(L"Surface",L"表面");XH_Add(L"User Interface",L"用户界面");
    auto ComboLabel=SNew(STextBlock).Text(FText::FromString(TEXT("Surface")));
    auto Rich=SNew(SRichTextBlock).Text(FText::FromString(TEXT("User Interface")));
    VisitWidget(ComboLabel);VisitWidget(Rich);
    if(ComboLabel->GetText().ToString()!=TEXT("表面") || Rich->GetText().ToString()!=TEXT("用户界面"))return 301;
    auto Missing=SNew(STextBlock).Text(FText::FromString(TEXT("CaptureFixtureUnknown")));
    VisitWidget(Missing);if(XH_CurrentCount()!=0)return 302;
    XH_Collect(1);VisitWidget(Missing);VisitWidget(Missing);
    if(XH_CurrentCount()!=1)return 303;
    XH_Collect(0);XH_Tick();
    if(XH_CurrentCount()!=1 || FString(XH_Current(0))!=TEXT("CaptureFixtureUnknown"))return 304;
    XH_AckCapture(1);if(XH_CurrentCount()!=0)return 305;
    XH_Collect(1);
    const FString Description(TEXT("CaptureFixtureDescription: This module must be placed before the force solver. Preserve {Value}, [Transient]CollisionValid and /Niagara/Modules/Collision/Collision.Collision."));
    auto A=MakeShared<FNiagaraMenuAction_Generic>(FNiagaraMenuAction_Base::FOnExecuteAction(),
        FText::FromString(TEXT("CaptureFixtureAction")),TArray<FString>{TEXT("CaptureFixtureCategory")},
        TOptional<FNiagaraFavoritesActionData>(),FText::FromString(Description),FText());
    IndexAction(A);
    if(!PendingKeys.contains(std::wstring(*Description)))return 306;
    // A real tooltip window is not necessarily a top-level visible editor window.
    const FString TooltipText(TEXT("CaptureFixtureTooltip: This explanation is displayed briefly in a separate tooltip window and must remain available until exported."));
    auto Tip=SNew(SToolTip).Text(FText::FromString(TooltipText));
    FSlateApplication::Get().SpawnToolTip(Tip,FVector2f(100,100));XH_Tick();
    FSlateApplication::Get().CloseToolTip();
    if(!PendingKeys.contains(std::wstring(*TooltipText)))return 307;
    XH_Tick();if(!PendingKeys.contains(std::wstring(*TooltipText)))return 308;
    XH_Add(*TooltipText,L"这是已完整翻译的悬浮说明。");VisitWidget(Tip);
    bool Found=false;for(auto& Pair:Bindings)if(auto W=Pair.Value->Widget.Pin())if(W->GetText().ToString()==TEXT("这是已完整翻译的悬浮说明。"))Found=true;
    if(!Found)return 309;
    // Input boxes remain unchanged even when the label has a translation.
    auto Edit=SNew(SEditableTextBox).Text(FText::FromString(TEXT("Surface")));VisitWidget(Edit);
    if(Edit->GetText().ToString()!=TEXT("Surface"))return 310;
    XH_Enable(0,0);
    if(ComboLabel->GetText().ToString()!=TEXT("Surface") || Rich->GetText().ToString()!=TEXT("User Interface"))return 311;
    XH_Collect(0);XH_Clear();PendingCapture.clear();PendingKeys.clear();Observed.clear();return 0;
}

#include "TooltipTests.inl"
#include "LabelTests.inl"

XH_EXPORT int XH_SelfTest() {
    // Run in an isolated test editor: static text, live getter, restoration,
    // external replacement, and weak-widget cleanup.
    if (!IsInGameThread() || !FSlateApplication::IsInitialized()) return -1;
    XH_Clear(); XH_Add(L"Initialize Particle", L"初始化粒子"); XH_Add(L"Particle State", L"粒子状态"); XH_Enable(1,0);
    FString Source(TEXT("Initialize Particle"));
    auto Widget = SNew(STextBlock).Text_Lambda([&Source] { return FText::FromString(Source); });
    VisitWidget(Widget);
    if (Widget->GetText().ToString() != TEXT("初始化粒子")) return 1;
    Source = TEXT("Particle State");
    if (Widget->GetText().ToString() != TEXT("粒子状态")) return 2;
    XH_Enable(0,0);
    Source = TEXT("Unmapped changed text");
    if (Widget->GetText().ToString() != Source) return 3;
    auto Static = SNew(STextBlock).Text(FText::FromString(TEXT("Initialize Particle")));
    XH_Enable(1,1); VisitWidget(Static);
    if (Static->GetText().ToString() != TEXT("初始化粒子 (Initialize Particle)")) return 4;
    Static->SetText(FText::FromString(TEXT("External owner changed value")));
    XH_Enable(0,0);
    if (Static->GetText().ToString() != TEXT("External owner changed value")) return 5;
    bool Entered = false;
    auto Editable = SNew(SInlineEditableTextBlock)
        .Text(FText::FromString(TEXT("Initialize Particle")))
        .OnEnterEditingMode_Lambda([&Entered]() { Entered=true; });
    XH_Enable(1,0); VisitWidget(Editable);
    Editable->EnterEditingMode();
    if (!Entered || Editable->GetText().ToString() != TEXT("Initialize Particle")) return 6;
    Editable->ExitEditingMode();
    XH_Enable(0,0);
    Entered=false;Editable->EnterEditingMode();
    if (!Entered) return 7;
    Editable->ExitEditingMode();
    XH_Add(L"Spawns a burst of particles instantaneously.",L"瞬间生成一批粒子。");
    auto Tooltip = SNew(SToolTip).Text(FText::FromString(TEXT("Spawns a burst of particles instantaneously.")));
    XH_Enable(1,0);VisitWidget(Tooltip);
    bool FoundTip=false;
    for (auto& Item : Bindings) {
        auto TextWidget=Item.Value->Widget.Pin();
        if (TextWidget.IsValid() && TextWidget->GetText().ToString()==TEXT("瞬间生成一批粒子。")) FoundTip=true;
    }
    if (!FoundTip) return 8;
    XH_AddLegacy(L"Particle",L"粒子");XH_AddLegacy(L"Particle State",L"粒子状态");
    if (Lookup(L"  INITIALIZE   PARTICLE \r\n") != L"初始化粒子")return 9;
    if (Lookup(L"Controls Particle State; particles remain.") != L"Controls Particle State; particles remain.")return 10;
    if (Lookup(L"ParticleSize Particles {Particle}") != L"ParticleSize Particles {Particle}")return 11;
    auto CachedText=SNew(STextBlock).Text(FText::FromString(TEXT("Initialize Particle")));
    auto CachedPanel=SNew(SInvalidationPanel)[CachedText];
    CachedPanel->SetCanCache(true);
    VisitWidget(CachedPanel,0,true);
    if(CachedText->GetText().ToString()!=TEXT("初始化粒子"))return 12;
    XH_Enable(0,0);
    if(CachedText->GetText().ToString()!=TEXT("Initialize Particle"))return 13;
    if(Lookup(L"Particle State Mode")!=L"Particle State Mode")return 14;
    if(Lookup(L"Particle State: {Value}")!=L"粒子状态: {Value}")return 15;
    XH_AddLegacy(L"Mode",L"模式");
    if(Lookup(L"Particle State Mode")!=L"粒子状态 模式")return 16;
    XH_Add(L"Particle State Mode",L"自定义粒子状态模式");
    if(Lookup(L"Particle State Mode")!=L"自定义粒子状态模式")return 17;
    XH_Add(L"DynamicMaterialParameter",L"动态材质参数");
    if(Lookup(L"DynamicMaterialParameter3")!=L"动态材质参数 3")return 18;
    XH_Add(L"DynamicMaterialParameter2",L"专用参数二");
    if(Lookup(L"DynamicMaterialParameter2")!=L"专用参数二")return 19;
    XH_Add(L"Vector",L"向量");
    if(Lookup(L"Vector3")!=L"Vector3")return 20;
    if(Lookup(L"Use DynamicMaterialParameter3 now")!=L"Use DynamicMaterialParameter3 now")return 21;
    XH_Clear(); return 0;
}
