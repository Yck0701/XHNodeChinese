using UnrealBuildTool;
public class BridgeBuild : ModuleRules {
    public BridgeBuild(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.NoPCHs;
        PublicDependencyModuleNames.AddRange(new string[]{"Core", "CoreUObject", "Slate", "SlateCore", "ApplicationCore", "InputCore", "NiagaraEditor", "NiagaraEditorWidgets"});
    }
}
