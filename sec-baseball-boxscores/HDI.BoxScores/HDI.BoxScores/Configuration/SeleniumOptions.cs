using OpenQA.Selenium;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;

namespace HDI.BoxScores.Configuration;

public sealed class SeleniumOptions
{
    [EnumDataType(typeof(PageLoadStrategy))]
    public PageLoadStrategy? PageLoadStrategy { get; init; }
    public long? PageLoadTimeoutSeconds { get; init; }
    public long? ImplicitWaitTimeoutSeconds { get; init; }
    public long? HttpCommandTimeoutSeconds { get; init; }
    public IEnumerable<string>? Arguments { get; init; }
    public IEnumerable<string>? ExcludedArguments { get; init; }
}