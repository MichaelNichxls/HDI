using System.ComponentModel.DataAnnotations;

namespace HDI.BoxScores.Configuration;

public sealed class GoogleOptions
{
    public string? ApplicationName { get; init; }
    [Required]
    public required string CredentialFile { get; init; }
    [Required]
    public required string SpreadsheetId { get; init; }
    [Required]
    public required string HittingSheetName { get; init; }
    [Required]
    public required string PitchingSheetName { get; init; }
}