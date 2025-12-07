using System.ComponentModel.DataAnnotations;

namespace HDI.BoxScores.Configuration;

public sealed class BoxScoreOptions
{
    public const string SectionName = "HDI.BoxScores";

    [Required]
    public required GoogleOptions Google { get; init; }
    public required SeleniumOptions Selenium { get; init; } = new();
}
