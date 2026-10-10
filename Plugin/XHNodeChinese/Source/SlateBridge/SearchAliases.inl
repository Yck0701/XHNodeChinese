// Search-only equivalences: display translations and asset identifiers stay intact.
// Keep groups narrow; antonyms such as opacity/transparency are not synonyms.
static TArray<FString> SearchAliases(const FString& Source) {
    TArray<FString> Result{Source};
    const TCHAR* Groups[][2]={{TEXT("尺寸"),TEXT("大小")},{TEXT("颜色"),TEXT("色彩")}};
    for(const auto& Group:Groups){
        const int32 Count=Result.Num();
        for(int32 I=0;I<Count && Result.Num()<32;++I){
            const FString Current=Result[I];
            for(int32 From=0;From<2;++From)
                if(Current.Contains(Group[From]))Result.AddUnique(Current.Replace(Group[From],Group[1-From]));
        }
    }
    return Result;
}
