// Whole-label aliases only. Paths, expressions and prose never enter this index.
// Build once on dictionary load; LookupCache also caches hits and misses.
using FLabelChoices = std::map<std::wstring, std::wstring>;
static std::map<std::wstring, FLabelChoices> LabelAliases;
static std::wstring LabelKey(const std::wstring& Source, bool Pattern=false) {
    if(Source.empty() || Source.size()>128)return {};
    std::wstring Key; bool Index=false;
    for(size_t I=0;I<Source.size();++I) {
        const wchar_t C=Source[I];
        if(C==L' ')continue;
        if(Pattern && Source.compare(I,7,L"{Index}")==0 && !Index) {
            Key+=L'#';Index=true;I+=6;continue;
        }
        if(!((C>=L'A' && C<=L'Z') || (C>=L'a' && C<=L'z')))return {};
        Key+=towlower(C);
    }
    return Key;
}
static void AddLabelAlias(const std::wstring& Source,const std::wstring& Translation) {
    auto Key=LabelKey(Source,true);if(Key.empty())return;
    if(Key.find(L'#')!=std::wstring::npos) {
        const auto At=Translation.find(L"{Index}");
        if(At==std::wstring::npos || Translation.find(L"{Index}",At+7)!=std::wstring::npos)return;
    }
    LabelAliases[Key][Normalize(Source).Text]=Translation;
}
static bool UniqueLabelAlias(const std::wstring& Key,std::wstring& Out) {
    const auto Found=LabelAliases.find(Key);
    if(Found==LabelAliases.end() || Found->second.empty())return false;
    const auto& Value=Found->second.begin()->second;
    for(const auto& Pair:Found->second)if(Pair.second!=Value)return false;
    Out=Value;return true;
}
static bool LookupLabelAlias(const std::wstring& Source,std::wstring& Out) {
    if(Source.empty() || Source.size()>128)return false;
    const auto Key=LabelKey(Source);
    if(!Key.empty())return UniqueLabelAlias(Key,Out);
    const auto Begin=Source.find_first_of(L"0123456789");
    if(Begin==std::wstring::npos)return false;
    auto End=Begin;while(End<Source.size() && Source[End]>=L'0' && Source[End]<=L'9')++End;
    // Only explicit templates can translate an index in the middle of a name.
    const auto Pattern=LabelKey(Source.substr(0,Begin)+L"{Index}"+Source.substr(End),true);
    if(!Pattern.empty() && UniqueLabelAlias(Pattern,Out)) {
        Out.replace(Out.find(L"{Index}"),7,Source.substr(Begin,End-Begin));return true;
    }
    return false;
}
