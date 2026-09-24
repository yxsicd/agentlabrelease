import { PaymentAuthorityScriptGenerator } from '../modules/payment/PaymentAuthorityPolicy'

@Entry
@Component
struct Index {
  private policyLabel(): string {
    const program = PaymentAuthorityScriptGenerator.classify(['agentlab.example'], ['nspk'])
    const merchantBranch = program.includes("result('merchant'")
    const providerBranch = program.includes("result('payment-provider'")
    return merchantBranch && providerBranch ? 'Multi Repo Ready' : 'Policy Missing'
  }

  build() {
    Column() {
      Text(this.policyLabel()).fontSize(24)
    }
      .width('100%')
      .height('100%')
      .justifyContent(FlexAlign.Center)
  }
}
