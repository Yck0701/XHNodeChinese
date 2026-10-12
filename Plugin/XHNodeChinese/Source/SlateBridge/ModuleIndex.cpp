// Read-only metadata extraction. Called on the editor thread, one asset per step.
// Reflection avoids depending on private Niagara object layouts.
#include "CoreMinimal.h"
#include "UObject/UObjectHash.h"
#include "UObject/UnrealType.h"
#include "UObject/TextProperty.h"
#include "UObject/StrProperty.h"
#include "UObject/UObjectGlobals.h"
#include "Internationalization/Text.h"
static TArray<FString> Texts;
static void Add(const FString& S) { if (!S.IsEmpty() && S != TEXT("None")) Texts.AddUnique(S); }
static void ReadValue(FProperty* P, const void* V, int Depth);
static void ReadStruct(const UStruct* S, const void* V, int Depth) {
    if (Depth>16) return;
    for (TFieldIterator<FProperty> It(S); It; ++It)
        for(int I=0;I<It->ArrayDim;++I) ReadValue(*It,It->ContainerPtrToValuePtr<void>(V,I),Depth+1);
}
static void ReadValue(FProperty* P, const void* V, int Depth) {
    if(Depth>16) return;
    const FString Name=P->GetName();
    if(auto T=CastField<FTextProperty>(P)) { Add(T->GetPropertyValue(V).ToString()); return; }
    if(auto S=CastField<FStructProperty>(P)) { ReadStruct(S->Struct,V,Depth+1); return; }
    if(auto A=CastField<FArrayProperty>(P)) {
        if(!CastField<FStructProperty>(A->Inner) && !CastField<FTextProperty>(A->Inner) && !CastField<FObjectPropertyBase>(A->Inner)) return;
        FScriptArrayHelper H(A,V); for(int I=0;I<H.Num();++I) ReadValue(A->Inner,H.GetRawPtr(I),Depth+1); return;
    }
    if(auto N=CastField<FNameProperty>(P)) {
        const FString Owner=P->GetOwnerStruct()->GetName();
        FString S=N->GetPropertyValue(V).ToString();
        if(Name==TEXT("Name") && Owner.StartsWith(TEXT("NiagaraVariable"))) {
            if(S.StartsWith(TEXT("Module."))) S.RightChopInline(7);
            if(!S.Contains(TEXT("."))) Add(FName::NameToDisplayString(S,false));
        } else if(Name.StartsWith(TEXT("OverrideName")) || Name==TEXT("CategoryName") || (Owner.Contains(TEXT("Hierarchy")) && (Name==TEXT("Name") || Name==TEXT("Category") || Name==TEXT("Section") || Name==TEXT("SectionName")))) Add(S);
        return;
    }
    if(auto S=CastField<FStrProperty>(P)) {
        if(Name==TEXT("NodeComment") || Name==TEXT("PinToolTip")) Add(S->GetPropertyValue(V));
        return;
    }
    if(auto O=CastField<FObjectPropertyBase>(P)) {
        // Enumerations are referenced assets; do not traverse arbitrary references.
        if(UEnum* E=Cast<UEnum>(O->GetObjectPropertyValue(V)))
            for(int I=0;I<E->NumEnums()-1;++I) { Add(E->GetDisplayNameTextByIndex(I).ToString()); Add(E->GetToolTipTextByIndex(I).ToString()); }
    }
}
extern "C" __declspec(dllexport) int XH_IndexAsset(const wchar_t* Path) {
    Texts.Reset(); if(!IsInGameThread()) return -2;
    UObject* Asset=StaticLoadObject(UObject::StaticClass(),nullptr,Path);
    if(!Asset) return -1;
    TArray<UObject*> Objects; GetObjectsWithOuter(Asset,Objects,true); Objects.Add(Asset);
    for(UObject* Object:Objects) ReadStruct(Object->GetClass(),Object,0);
    return Texts.Num();
}
extern "C" __declspec(dllexport) const wchar_t* XH_IndexText(int I) { return Texts.IsValidIndex(I)?*Texts[I]:TEXT(""); }
