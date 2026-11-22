"""First-name gender prior: names that are overwhelmingly one gender in US public birth records.

Source: US Social Security Administration, "Beginning with Baby Names" national file (names given to at least five
babies a year, 1880-2017, summed over every year). SSA data is a US government work in the public domain; it was read
from the CRAN `babynames` package (CC0). Derived table: a name is listed only with at least 2000 births and at
least 95% of them one gender (3517 female, 2147 male names). Regenerate with
`scripts/maintenance/build_first_name_prior.py`.

Use: a casting steer only (`persona.gender.gender_lean`). It never writes a gender into the graph, and a name that is
absent here (most translated xianxia names) stays unknown (non-negotiables 4 and 9: precision over recall).
"""

from __future__ import annotations

_FEMALE = """
aaliyah aanya abagail abbey abbie abbigail abbigale abby abbygail abigail abigale abigayle
abriana abrianna abrielle abril abygail acacia ada adah adalee adaline adalyn adalynn adamaris
addie addilyn addilynn addisyn addyson adela adelaida adelaide adele adelia adelina adeline
adella adelle adelyn adelynn adia adilene adina aditi adria adriana adriane adrianna adrianne
adriene adrienne adyson agatha agnes aida ailani aileen ailene ailyn aimee ainsley aisha aislinn
aiyana aiyanna aja akilah alaina alana alanah alani alanis alanna alannah alaya alayah alayna
alaysia alba alberta albertha albertine albina alda alea aleah alecia aleen aleena aleigha
aleisha alejandra aleksandra alena alene alesha aleshia alesia alessandra alessia aleta aletha
alethea alethia alexa alexandra alexandrea alexandria alexia alexsandra alexus alfreda alia
aliah aliana alianna alice alicia alida alina aline alisa alise alisha alishia alisia alison
alissa alisson alivia aliya aliyah aliza allana allegra allene alli allison allissa allisson
alliyah ally allysa allyson allyssa alma almeda almeta alona alondra alonna alora alta altha
althea alvera alverta alvina alyce alycia alyna alysa alyse alysha alysia alyson alyssa alyssia
alyvia amada amalia amanda amara amaria amariah amaris amaya amayah ambar amber amberly ameera
amelia amelie america amethyst ami amia amiah amie amina aminah amira amirah amiya amiyah ammie
amora amparo amy amya amyah ana anabel anabella anabelle anahi anai anais analia analisa analise
anamaria ananya anastacia anastasia anaya anayah anayeli andrea andria anessa anette angela
angelena angeles angelia angelic angelica angelika angelina angeline angelique angelita angella
angely angelyn angie ani ania aniah anika anisa anisha anissa anita anitra aniya aniyah anja
anjali anjanette anjelica ann anna annabel annabell annabella annabelle annalee annaliese
annalisa annalise annamae annamaria annamarie anne anneliese annelise annemarie annetta annette
annie annika annis anniston annmarie ansley antionette antoinette antonella antonette antonina
anya april apryl arabella araceli aracely araya ardella ardith areli arely aretha aria ariadna
ariadne ariah ariana ariane arianna arianne arica ariela ariella arielle arika arionna arissa
ariya ariyah ariyana ariyanna arizona arla arleen arlena arlene arleth arletta arlette arline
armida arnetta arnita arvilla arwen aryana aryanna asha ashely ashia ashlea ashlee ashlei
ashleigh ashley ashli ashlie ashly ashlyn ashlynn asia astrid athena aubree aubri aubriana
aubrianna aubrie aubrielle audra audrea audree audrey audriana audrianna audrie audrina
augustina aundrea aura aurelia aurora autum autumn ava avah avalon avalyn avalynn avani averi
averie aviana avianna avis aviva avril aya ayah ayana ayanna ayesha ayla ayleen aylin aysha
aysia ayva azalea azaria azucena azul babette baila bailee baileigh bambi barb barbara barbie
barbra baylee bayleigh baylie beatrice beatrix beatriz beaulah becca becki beckie becky belen
belia belinda bella belle belva benita berenice bernadette bernadine bernardine berneice
bernetta bernice berniece bernita berta bertha bess bessie beth bethanie bethann bethany betsey
betsy bette bettie bettina betty bettye beulah beverlee beverley beverly bianca bianka billye
birdie blaire blanca blanch blanche blossom blythe bobbi bobbye bonita bonnie bonny braelynn
brandee brandi brandie brandy braylee brea breana breann breanna breanne bree breeanna brenda
brenna breonna bria briana brianna brianne bridget bridgett bridgette brie brieanna briella
brielle brigette brigid brigitte brinda brinley brionna brisa briseida brissa britany britney
britni britta brittaney brittani brittanie brittany brittnee brittney brittni brittnie brittny
bronwyn brooke brookelyn brookelynn brooklyn brooklynn bryana bryanna brylee bryleigh brynlee
brynn brynna brynne buffy bulah cady caelyn cailey cailin cailyn caitlin caitlyn caitlynn
caleigh cali calista calla calli callie calliope callista cambria camelia camellia cami camila
camilla camille cammie candace candance candelaria candi candice candida candie candis candy
candyce capri cara caren cari carie carin carina carisa carissa carla carlee carleen carleigh
carlene carletta carley carli carlota carlotta carly carlyn carma carmela carmelita carmella
carol carolann carole carolee carolina caroline carolyn carolyne carolynn carri carrie caryn
carys casandra casie cassandra cassaundra cassi cassie cassondra cataleya catalina catarina
catelyn caterina catharine catherine cathey cathi cathie cathleen cathrine cathryn cathy catina
catrina cayla caylee caylin cecelia cecile cecilia cecily celena celesta celeste celestina
celestine celia celina celine ceola chana chanda chandra chanel chanell chanelle chantal chante
chantel chantell chantelle charis charise charisma charissa charisse charity charla charlee
charleen charleigh charlene charlette charli charline charlize charlotte charlsie charmaine
charolette chasidy chasity chassidy chassity chastity chava chaya chelsea chelsey chelsi chelsie
chelsy cheree cheri cherie cherilyn cherise cherish cherri cherrie cherry cheryl cheryle cheryll
cheyanne cheyenne chiara china chiquita chloe chrissy christa christal christeen christel
christena christene christi christiana christiane christianna christie christina christine
christy chrystal chyanne chyna chynna ciana cianna ciara ciarra cicely cielo cienna ciera cierra
cinda cindi cindy cinnamon cinthia citlali citlalli citlaly claire clara claribel clarice
clarisa clarissa claudette claudia claudine clementine cleopatra cleta cloe clover coleen
coletta colette colleen collette concetta connie constance consuelo cora coral coralee coralie
coraline cordelia coreen corene coretta corina corine corinna corinne corissa cornelia corrina
corrine corrinne cosette courtnie crissy crista cristal cristen cristi cristie cristin cristina
cristine cristy crystal cydney cyndi cynthia dacia dafne dahlia daija daijah daina daisey daisha
daisy daja daleyza dalia dalila dalilah damaris danae danelle danette dania danica daniela
daniella danielle danika danisha danita danna dannette danni dannielle danya danyelle daphne
dara darcey darci darcie daria dariana darla darleen darlene darline dasha dasia davida davina
dawn dawna dawne dayana dayanara dayanna dayna daysha deana deann deanna deanne deasia debbi
debbie debbra debby debi debora deborah debra debrah dedra deeann deedee deedra deena deidra
deidre deirdre deisy deja dejah delana delaney delanie delena delfina delia delicia delila
delilah delinda delisa della delois delora delores deloris delpha delphia delphine delta demetra
demetria demi dena denae deneen denice denise denisha denisse denita denna dennise deonna
desirae desire desiree dessie destany destinee destiney destini destinie destiny detra devona
devora devorah dian diana diane diann dianna dianne dimple dina dinah dionna dionne divya dixie
diya dollie dolly dolores domenica dominga dominica dona donielle donita donna dora dorcas
doreen dorene doretha doretta dori dorinda dorine doris dorotha dorothea dorothy dortha dorthea
dorthy dottie dovie dreama drema drucilla drusilla dulce dynasty earlean earlene earline
earnestine eartha easter eboni ebonie ebony echo eda edie edith edna edwina edyth edythe effie
eileen eilene elaina elaine elana elayna elayne elda eldora eleanor eleanora eleanore elease
elena eleni elenor elenora elexis eliana elianna elicia elida elin elina elinor elinore elisa
elisabeth elise elissa eliza elizabeth elizebeth ella elle ellen ellena elli elliana ellianna
ellie elly ellyn elma elmira elna elnora elodie elois eloisa eloise elora elouise elsa elsie
elva elvera elvia elvina elvira elyse elysia elyssa ema emalee ember emelia emelie emeline emely
emelyn emerie emersyn emi emilee emilia emilie emily emma emmalee emmaleigh emmaline emmalyn
emmalynn emme emmeline emmer emmie emmy emogene ena enedina enid enola era erica ericka erika
erin erinn erlene erlinda erma erna ernestina ernestine eryn esme esmeralda esperanza essence
essie esta estefani estefania estefany estela estella estelle esther estrella ethel ethelyn
ethyl etta eudora eugenia eugenie eula eulalia euna eunice eva evalyn evalynn evangelina
evangeline eve evelin evelina eveline evelyn evelyne evelynn everleigh everly evette evie evonne
exie fabiola fae faigy fairy faith fallon fannie fanny farah farrah fatima fatimah fawn faye
felecia felica felicia felicity felipa felisa felisha fern fernanda ferne filomena fiona flo
flor flora florence florene floretta florida florine flossie floy fonda frances francesca
franchesca francine francisca freda frederica fredia freeda freida freya frida frieda gabriela
gabriella gabrielle gail galilea gaye gayla gaylene gaynell gearldine gema gemma gena genesis
geneva genevieve genna genoveva georgeann georgene georgetta georgette georgia georgiana
georgianna georgina georgine geraldine geralyn geri gerri gertie gertrude gia giada giana gianna
giavanna gigi gilda gillian gina ginger ginny giovanna gisel gisela gisele giselle gissel
gisselle gitty giulia giuliana gizelle gladis gladys glenda glendora glenna glinda gloria glory
glynda glynis golda goldie grace gracelyn gracelynn gracey gracie graciela gracyn grayce grecia
gregoria greta gretchen gretta griselda guinevere gwen gwenda gwendolyn gwenyth gwyneth hadassah
hadlee hadleigh hailee hailey hailie haily halee haleigh haley hali halie halle halley hallie
hana hanna hannah harleigh harmoni harmonie harmony harriet harriett harriette hattie haydee
haylee hayleigh hayley haylie hazel hazle heather heaven heavenly hedwig hedy heide heidi heidy
helen helena helene helga hellen henrietta herlinda herminia hester hettie hilda hildegarde
hillary hilma holley holli holly honesty honey hope hortencia hortense hulda ida idalia idell
idella iesha ila ilana ileana ileen ilene iliana ilona ilse ima imani imelda imogene ina india
indira inell inez inga ingrid iola iona ione ireland irene iris irma isabel isabela isabell
isabella isabelle isadora isamar isela isha isis isla isobel italia itzayana itzel iva ivana
ivanna ivette ivonne iyana iyanna izabel izabella izabelle jacalyn jacelyn jaci jacie jacinda
jacinta jackeline jackelyn jacki jacklyn jacklynn jaclyn jaclynn jacqualine jacquelin jacqueline
jacquelyn jacquelyne jacquelynn jacquline jacqulyn jada jaeda jaela jaelynn jaida jaila jailene
jaimee jakayla jaleah jaleesa jalisa jalissa jaliyah jamaya jamesha jami jamia jamila jamilah
jamiya jamiyah jamya jana janae janai janay janaya jane janee janeen janel janell janelle janene
janessa janet janeth janett janetta janette janey jania janiah janice janie janiece janina
janine janis janise janiya janiyah janna jannet jannette jannie january janya jaquelin jaqueline
jaquelyn jaslene jaslyn jasmin jasmine jasmyn jasmyne jaunita jaya jaycie jayda jayde jayla
jaylah jaylee jayleen jaylene jaymee jayna jayne jazelle jazlyn jazlynn jazmin jazmine jazmyn
jazmyne jazzlyn jazzmin jazzmine jean jeana jeane jeanelle jeanene jeanetta jeanette jeanie
jeanine jeanmarie jeanna jeanne jeannette jeannie jeannine jemma jena jenae jenell jenelle
jenesis jenessa jeni jenifer jeniffer jenine jenise jenna jennah jennette jenni jennie jennifer
jenniffer jenny jeraldine jeri jerica jerilyn jerri jerrica jesenia jesica jessa jessalyn
jessenia jessica jessika jesslyn jetta jianna jill jillian jimena jiselle jo joan joana joanie
joann joanna joanne jocelin jocelyn jocelyne jocelynn jodee jodi joella joelle joellen joetta
joette johana johanna johannah johna johnetta johnette johnna joi jolee joleen jolene jolie
joline jolynn jonelle joni jonna jordana jordynn jorja joscelyn josefa josefina joselin joseline
joselyn josephina josephine josette josie joslyn joslynn josselyn journee jovanna jovita joy
joyce joycelyn joye juana juanita jubilee judi judie judith judy julee juli julia juliana
juliane juliann julianna julianne julie julieann julienne juliet julieta juliette julisa julissa
june juniper jurnee justina kaci kacie kadie kady kaela kaeli kaelyn kaelynn kaia kaila kailani
kailee kaileigh kailey kaili kaily kailyn kailynn kaira kaitlin kaitlyn kaitlynn kaiya kala
kalea kaleah kalee kaleigh kalena kaley kali kalia kalie kalina kalista kaliyah kalli kallie
kalyn kalynn kamaria kami kamila kamilah kamille kamiya kamiyah kamora kamya kandace kandi
kandice kandis kandy kanisha kaniya kara karah karen karena kari karie karime karin karina karis
karisa karissa karla karlee karleen karleigh karlene karley karli karlie karly karlyn karma
karmen karolina karoline karolyn karren karri karrie karyl karyn kasandra kasi kasie kassandra
kassi kassidy kassie katalina katarina kate katelin katelyn katelynn kateri katerina katey
kathaleen katharine katherin katherine kathern katheryn katheryne kathi kathie kathleen kathlene
kathlyn kathrine kathryn kathryne kathy kathyrn kati katia katie katina katlin katlyn katlynn
katrice katrina kattie katy katya kay kaycee kaycie kaydee kaydence kaye kayla kaylah kaylani
kaylea kaylee kayleen kayleigh kaylene kayley kayli kaylie kaylin kaylyn kaylynn kaytlin kaytlyn
keana keanna keara kecia keeley keely keesha keila keilani keily keira keisha kelci kelcie keli
kelis kelle kellee kelli kellie kellye kelsea kelsey kelsi kelsie kelsy kenda kendra kendyl
kenia kenisha kenna kennedi kensington kensley kenyetta kenzi kenzie keona kera keren keri kerri
kerrie kerrigan kerstin kesha keshia keturah keyana keyanna keyla keyona keyonna keziah khadija
khadijah khalia khloe kia kiana kianna kiara kiarra kiera kierra kiersten kierstin kierstyn
kiesha kimber kimberely kimberlee kimberley kimberli kimberlie kimberly kimberlyn kimora kindra
kinley kinsey kinslee kinsley kira kirra kirsten kirstie kirstin kirstyn kisha kittie kitty kiya
kizzy klara klarissa kloe kora korina krissy krista kristal kristel kristen kristi kristiana
kristie kristin kristina kristine kristy kristyn krysta krystal krysten krystin krystina krystle
kya kyah kyana kyara kyla kylah kylee kyleigh kyli kylie kymberly kyndal kyndall kyndra kynlee
kyra lacee lacey lachelle laci lacie ladonna laila lailah laina lainey laisha lakeisha lakendra
lakesha lakeshia lakia lakisha lakyn lana lanae lanette laney lani lanie lanita laniya laniyah
lanora laquisha laquita lara larae laraine larhonda larisa larissa laronda lashanda lashawnda
lashay lashonda lashunda latanya latasha latavia latesha latia laticia latina latisha latonia
latonya latoria latosha latoya latrice latricia latrina launa laura lauralee laureen laurel
lauren laurene lauretta laurette lauri laurie laurine lauryn lavada lavera laverna lavina
lavinia lavonda lavonne lawana lawanda lawanna layla laylah layna lea leah leana leandra leann
leanna leanne leatha leatrice leda leeann leeanna leeanne leela leena leesa leia leigha leighann
leila leilah leilani leilany leisa lela lelah lelia lena lenna lenora lenore leola leona leone
leonor leonora leonore leora leota lera lesa lesia leslee lesli lesly leslye leta letha leticia
letitia lettie letty lexi lexie lexis lexus lexy leyla lezlie lia liana liane lianna lianne
libbie libby liberty lida lidia lila lilah lili lilia lilian liliana lilianna lilith lilla lilli
lillia lillian lilliana lillianna lillie lilly lillyan lillyana lillyanna lily lilyan lilyana
lilyann lilyanna lina linda lindsay lindsey lindsy linette linnea linsey lisa lisbeth lise
lisette lisha lissa lissette lita litzy liv livia liz liza lizabeth lizbeth lizet lizeth lizette
lizzie lluvia lois lola lolita loma lona londyn loni lonna lora loraine loree loreen lorelai
lorelei lorena lorene loretta lori loriann lorie lorinda lorine lorna lorraine lorretta lorri
lorrie lottie louann louella louisa louise lourdes louvenia lovina lu luana luann luanne lucero
luci lucia luciana lucie lucila lucile lucille lucinda lucretia lucy luella luetta luisa lula
lulu luna lupita lura luvenia luz lyda lydia lyla lylah lynda lyndsay lyndsey lynelle lynette
lynne lynnette lynsey lyra mabel mabelle mable macayla macey machelle maci macie mackenna macy
madaline madalyn madalynn maddie maddison madelaine madeleine madelene madelin madeline madelyn
madelyne madelynn madge madie madilyn madilynn madisen madison madisyn madlyn madonna madysen
madyson mae maegan maeve magali magaly magan magda magdalen magdalena magdalene magen maggie
magnolia mahala mahogany mai maia maida maile maira maisie maisy maite maiya makaela makaila
makala makayla makaylah makena makenna makenzi makenzie makiya makiyah makyla malaika malaya
malayah malaysia malea maleah malena malia maliah malika malina malinda malisa malissa maliyah
malka mallorie mallory malorie mamie mammie manda mandi mandie mandy manuela mara marah maranda
marcela marcelina marceline marcella marci marcia marcie marcy mardell marely maren margaret
margarete margarett margaretta margarette margarita margaux marge margery margie margo margot
margret marguerite mari maria mariah mariam marian mariana mariann marianna marianne maribel
maribeth maricela maricruz marie mariel mariela mariella marielle marietta marika marilee
marilou marilu marilyn marilynn marina marisa marisela marisol marissa marita maritza marivel
mariya mariyah marjorie marjory markayla markita marla marlana marlee marleen marleigh marlena
marlene marli marlie marlys marna marni marnie marquetta marquita marsha marta martha marti
martina marva mary marya maryalice maryam maryann maryanna maryanne marybeth maryellen maryjane
maryjo marylee marylin marylou marylyn marylynn maryn maryrose mathilda matilda mattie maud
maude maudie maura maureen maurine mavis maxine may maya mayah maybell maybelle maycee maylee
maylin mayme mayra mayte mazie mckayla mckenna mckenzie meadow meagan meaghan mechelle meera meg
megan meggan meghan meghann melaine melani melania melanie melany melba melia melina melinda
melisa melissa mellie mellisa mellissa melodee melodie melody melonie melony melva melvina
melynda meranda mercedes mercedez mercy meri meridith merilyn merissa merlene merna merri merrie
merry meta mia miah micaela micayla michaela michaella michela michele michelina michelle micki
miesha migdalia mignon mikaela mikaila mikala mikayla mikki mila milagros milana milani milania
mildred milena miley milissa millicent millie milly mimi mina mindi mindy minerva minna minnie
mira miracle miranda mirella mireya miriam mirian mirna missy misti mistie misty mittie mitzi
miya miyah moira mollie molly mona monae monet monica monika monique monserrat montserrat moriah
mozelle muriel mya myah myesha myia mykayla myla mylah mylee myra myranda myriam myrna myrtice
myrtie myrtis myrtle nada nadia nadine nadya nahla nailah naima nakisha nakita nala nalani
nallely nan nanci nancie nancy nanette nannette nannie naoma naomi nariah natalee natali natalia
natalie nataly natalya natasha natashia nathalia nathalie nathaly natosha nautica naya nayeli
nayely nayla nechama neda nedra neha nelda nell nella nelle nellie nelly nena neoma nereida
neriah neta nettie neva nevaeh neveah nia nichelle nichol nichole nicki nickole nicol nicole
nicolette nicolle nidia niesha nika niki nikki nikole nila nilda nina ninfa nisha nita niya
niyah noelani noelia noella noelle noemi nola nona nora norah noreen norene norine norma novella
nubia nya nyah nyasia nydia nyla nylah octavia odalis odalys odelia odessa odette ofelia ola
oleta olga olive olivia olympia olyvia oma ona oneida opal ophelia oralia oriana orpha ouida
ozella paige paislee paisley paityn palma paloma pam pamala pamela pamelia pamella pandora pansy
paola passion patience patrica patrice patricia patrina patti pattie patty paula pauletta
paulette paulina pauline pearl pearle pearlie pearline peggie peggy peighton penelope penni
pennie penny peri perla persephone petra petrina phebe phillis philomena phoebe phylicia phylis
phyliss phyllis pia pinkie piper polly poppy porsche porsha portia precious preslee pricilla
princess priscila priscilla priya prudence pyper qiana queen queenie quiana rachael racheal
rachel rachele rachell rachelle racquel rae raeann raechel raegan raelene raelyn raelynn rafaela
raina ramona rana ranae randa randi rania raquel rashida ravyn raya raylee raylene raylynn rayna
reanna reatha reba rebbecca rebeca rebecca rebecka rebeka rebekah rebekka reem reena regena
regenia regina reina rena renae renata renea renee renita reta retha retta reva reyna rhea
rhianna rhiannon rhoda rhonda ria riana rianna richelle rihanna rileigh rilla rilynn rina risa
rita rivka riya roberta robyn rochel rochelle rocio rolanda romina romona rona ronda ronna ronni
rori rosa rosalba rosalee rosalia rosalie rosalina rosalind rosalinda rosaline rosalva rosalyn
rosalynn rosamond rosana rosann rosanna rosanne rosaria rosaura rose roseann roseanna roseanne
rosella roselyn rosemarie rosemary rosetta rosia rosie rosina rosio rosita roslyn rowena roxana
roxane roxann roxanna roxanne roxie roxy rozella rubi rubie ruby rubye ruth rutha ruthann
ruthanne ruthie ryanne ryleigh saanvi sabina sabine sabra sabrina sade sadie sahar sahara saira
salena salina sallie sally salma samantha samara samaria samatha samaya samia samira samiya
samiyah samone samya sana sanaa sanai sandi sandie sandra saniya saniyah sanjana sanjuana
sanjuanita santa santina sapphire sara sarah sarahi sarai saray sarena sari sariah sarina sarita
sariyah sasha saundra savana savanah savanna savannah scarlet scarlett scarlette seanna sebrina
selah selena selene selina selma serafina serena serene serenity serina shaelyn shaila shaina
shakia shakira shala shalonda shameka shamika shamya shana shanae shanaya shanda shandra shaneka
shanel shanell shanelle shani shania shanice shanika shaniqua shanita shaniya shaniyah shanna
shanta shante shantel shantell shantelle shanya shaquana shaquita shara sharee sharen shari
sharita sharla sharleen sharlene sharon sharonda sharron sharyl sharyn shasta shauna shaunna
shavonne shawanda shawna shawnda shawnee shawnna shayla shaylee shaylyn shaylynn shayna sheena
sheila sheilah shelba shelbi shelbie shelia shelley shelli shelly shena sheree sheri sherie
sherilyn sherita sherlyn sherri sherrie sherry sherryl sheryl sheyla shianne shiela shira
shirlee shirlene shirley shivani shona shonda shonna shoshana shreya shyann shyanne shyla sibyl
siena sienna siera sierra signe sigrid silvana silvia simona simone simran sindy siobhan sirena
siri skyla skylynn sloane sofia sofie soledad soleil somer sommer sondra sonia sonja sonya
sophia sophie soraya spring staci stacia stacie star starla starr stasia stefani stefania
stefanie stefany steffanie stella stephaine stephani stephania stephanie stephany stephenie
stormie sudie sue sueann suellen summer sunday sunshine suri susan susana susann susanna
susannah susanne susie suzan suzann suzanna suzanne suzette suzie suzy sybil syble sydnee sydni
sydnie sylvia sylvie symone symphony synthia tabatha tabetha tabitha tahlia taina taisha takisha
tala taleah talia taliah talisa talisha talitha taliyah tallulah talya tamala tamara tamatha
tameka tamela tamera tami tamia tamica tamie tamika tamiko tamira tamisha tammara tammi tammie
tammy tamra tamya tamyra tana tanaya taneisha tanesha tangela tania tanika tanisha taniya
taniyah tanja tanna tanya tara tarah taraji tari tarra tarsha taryn tasha tashia tasia tatiana
tatianna tatiyana tatyana tavia tawana tawanda tawanna tawny tawnya taya tayla taylar tea teanna
teena temperance tena tenisha tenley tennie tennille tequila tera teresa terese teresita teressa
teri terra terri terrie tesla tess tessa tessie thais thalia thea theda thelma theodora theola
theresa therese theresia theressa thomasina thomasine thora thresa tia tiana tianna tiara tiarra
tiera tierney tierra tiesha tiffaney tiffani tiffanie tiffany tiffiny tillie tina tinley tinsley
tionna tisha tomasa tomeka tomi tomika tonda toni tonia tonisha tonja tonya tori tosha tova
towanda toya tracee traci tracie treasure trena tresa tressa tressie treva tricia trina triniti
trinity trish trisha trista trudi trudie trudy trula tuesday twana twila twyla tyana tyanna
tyasia tyesha tyla tyra una ursula vada valarie valencia valentina valeria valerie valery vallie
valorie vanesa vanessa vania vanita vannessa vashti veda velda velia vella velma velva velvet
vena venessa venita venus vera verda vergie verla verna vernetta vernita verona veronica
veronika versie vesta veta vianey vianney vickey vicki vickie vicky victoria vida vienna vikki
viktoria vilma vina vincenza viola violet violeta violetta violette virgie virginia viridiana
vita viva vivian viviana vivianna vivianne vivien vivienne vonda wanda waneta wanita wendi
wendie wendy wilda wilhelmina willa willene willette willow wilma windy winifred winnie
winnifred winona wynona wynter xenia ximena xiomara xitlali xochitl yadira yahaira yajaira
yamilet yamileth yaneli yanet yanira yara yareli yarely yaretzi yaretzy yaritza yasmeen yasmin
yasmine yazmin yazmine yesenia yesica yessenia yessica yetta yolanda yolonda yoselin yuliana
yulissa yuridia yvette yvonne zada zadie zahara zahra zaida zainab zaira zakiya zana zandra
zaniya zaniyah zara zaria zariah zariyah zaylee zelda zella zelma zena zenaida zenobia zetta
zina zipporah zita zoe zoey zoie zola zona zora zoraida zoya zula zulema
"""

_MALE = """
aaden aarav aaron aarush abdiel abdul abdullah abdulrahman abe abel abelardo abner abraham abram
ace achilles acie adalberto adam adan adelbert aden adin aditya adnan adolfo adolph adolphus
adonis adriano aedan agustin ahmad ahmed ahmir aidan aiden ajay akash akeem al alain alan alaric
albert alberto albin aldo alec alejandro alek aleksander alen alessandro alex alexander
alexandre alexandro alexzander alfonso alfonzo alford alfred alfredo alistair allan allen alonso
alonza alonzo aloysius alphonse alphonso alphonzo alston alton alvaro alvin amado amador amarion
ambrose ameer americo amin amir ammar ammon amon amos anakin anastacio anders anderson andrae
andre andreas andrei andres andrew andrey andy angelo angus anibal anish ansel anselmo anson
anthoney anthony antione antoine anton antone antonio antony antwain antwan antwon antwone anwar
apollo aram arch archer archibald archie ares aric arik arjun arlan arlo armaan arman armand
armando armin armon armond arnav arne arnold arnoldo arnulfo aron arron arsenio art artemio
arther arthur arturo arvel arvid arvil arvin aryeh asher atticus augustin augustus aurelio
austin auston auther author authur avraham avrohom axel axl axton ayaan ayden aydin baldemar
baltazar barney baron barrett barron barry bart bartholomew barton basil baxter beau beck
beckett beckham ben benedict benicio benito benjaman benjamen benjamin benjiman bennett benny
benson bently benton bernard bernardo bert bertram bertrand bilal bill billy bishop bjorn blain
blaine blane blas bob bobby bode boden bodhi bodie booker boone boris bowen boyce boyd brad
braden bradford bradley bradly bradon brady bradyn braeden braedon braiden brain brandan branden
brandin brandon brandt brannon branson brant brantley braulio braxton brayan brayden braydon
braylon brayson brayton brendan brenden brendon brennen brennon brent brenton bret brett brian
brice bridger brien briggs brigham brion broc brock broderick brodie brody bronson brooks bruce
bruno bryan bryant bryce brycen bryon brysen bryson buck bud buddy buford burke burl burley burt
burton buster butch byron cade caden cael caesar caiden cain cal cale caleb callum calvin camilo
camron candelario candido cannon cardell carl carleton carlo carlos carlton carlyle carmelo
carmine carsten carter carver case casen cash casimir cason casper cassius cayden cayson ceasar
cecilio cedric cedrick celestino celso cesar chace chad chadd chadrick chadwick chaim chance
chancellor charles charlton chas chase chaz chester chet chip christ christian christofer
christoper christophe christopher christos chuck cian cipriano ciro clarance clarence clark
claud claude claudio clay clayton clem clement clemente cleophus cletus cleve cleveland cliff
clifford clifton clint clinton clive cloyd clyde coby codey cody coen cohen cole coleman coleton
colin collin colson colt colten colter coltin colton columbus conner connor conor conrad conrado
constantine conway cooper corban corbett corbin cordell corey cormac cornelious cornelius
cornell cortez corwin cory cosmo craig crawford creed creighton crew cristian cristiano
cristobal cristofer cristopher cullen curt curtis curtiss cy cyril cyrus dajuan dallin dalton
damarcus damarion damen dameon damian damien damion damon damond dan dandre dane dangelo danial
daniel danilo danny dante daquan darel darell daren darin dario darius darold daron darrel
darrell darren darrick darrin darrion darris darrius darron darryl darvin darwin dash dashaun
dashiell dave daven daveon davey davian david davin davion davis davon davonte dawson dax daxton
daylan daylon dayton deacon dean deandre deangelo deante deanthony declan dedrick deegan deion
dejon dejuan delano delbert delfino delmar delmas delmer delton delvin demarco demarcus demario
demarion demetri demetrio demetrios demetrius demond demonte denis dennis denny denton denzel
denzil deondre deonta deontae deonte dequan derald dereck derek deric derick derik deron derrek
derrell derrick derrik derwin desean deshaun desmond dev devante devaughn devonta devontae
devonte dewayne dewey dewitt dexter dezmond dhruv dick diego dilan dillan dillard dillion dillon
dimitri dimitrios dino dionte dirk dixon dmitri dock domenic domenick domenico domingo dominic
dominick dominik domonic don donal donald donato donavan donavin donavon donn donny donovan
donta dontae dontay donte dontrell doran doug douglas douglass dov dovid doyle drake draven
duane dudley duke duncan durward durwood dustin dustyn duwayne dwain dwaine dwane dwayne dwight
dylan dylon eamon ean earl earle earnest easton eben ed edd eddy eder edgar edgardo edison
edmond edmund edmundo edsel edson eduardo edward edwardo edwin efrain efren elam elbert elden
eldon eldridge eleazar elgin eli elian elias eliel eliezer elijah elio eliseo eliyahu ellsworth
elmer elmo elmore eloy elroy elton elvin elvis elwin elwood elwyn emanuel emil emiliano emilio
emir emmanuel emmet emmett emmit emmitt enoch enos enrico enrique enzo ephraim erasmo eriberto
eric erich erick erik ernest ernesto ernie ernst errol ervin erwin esau esequiel esteban estevan
ethan ethen eugene eugenio eusebio evan evans everardo everett everette evert ewan ewell ezekiel
ezequiel ezra fabian fabio faris faron faustino fausto favian federico feliciano felipe felix
felton ferdinand fermin fernando fidel fidencio filiberto finis finn finnegan finnian fisher
flavio fletcher flint florencio florentino florian floyd ford forest forrest foster fox
francesco francisco franco frank franklin franklyn franky fransisco franz frazier fred freddy
frederic frederick fredric fredrick fredy freeman fritz fulton furman gabe gabino gabriel gael
gaetano gage gaige galen gannon gardner gareth garett garfield garland garner garold garret
garrett garrick garrison garry garth garvin gary gaston gatlin gauge gaven gavin gavyn gaylord
gearld geary genaro general gennaro geno geoffrey george geovanni geovanny gerald geraldo gerard
gerardo gerhard german gerold geronimo gerrit gerson gian giancarlo gianluca gibson gideon gil
gilbert gilberto giles gino giovani giovanni giovanny giuseppe glen glendon glenn glenwood
godfrey gonzalo gorden gordon gorge grady graeme graham grant granville graydon grayson green
greg gregg greggory gregorio gregory greyson griffin grover guido guillermo gunnar gunner gus
gustav gustave gustavo guy haden hakeem hakim hal hamilton hampton hamza hank hans hansel hardy
harlan harland harlen harmon harold harrell harris harrison harry harvey hasan haskell hassan
hayes hayward haywood heath heber hector henderson henery henrik henry herb herbert heriberto
herman hermon hernan herschel hershel heyward hezekiah hilario hilbert hillard hilton hiram
hobart hobert holden homer homero horace horacio hosea houston howard howell hoyt hubert hudson
huey hugh hugo humberto hunter hurley hussein huston hyman hyrum iain ian ibrahim idris ignacio
ignatius ike iker ilan immanuel imran irvin irving irwin isaac isaak isac isadore isai isaiah
isaias ishaan ishan ishmael isiah isidore isidro ismael ismail israel isreal issac ivan izaac
izaak izaiah izayah jabari jace jacen jacinto jack jackson jacob jacobo jacoby jacorey jacques
jad jadiel jadon jaedon jagger jaheim jair jairo jairus jajuan jake jakob jakobe jakub jaleel
jalen jalil jalon jamaal jamal jamar jamarcus jamarion jameel jamel jamell james jameson jamil
jamin jamir jamon jaquan jarad jared jarell jaren jaret jarett jarod jaron jarred jarrell jarren
jarret jarrett jarrod jarvis jase jasen jashawn jason jasper javan javen javian javier javin
javion javon javonte jax jaxen jaxon jaxson jaxton jay jayceon jaycob jaydon jaylon jaymes
jaysen jayson jayvion jayvon jaziel jeb jed jedediah jedidiah jeff jefferey jefferson jeffery
jeffrey jeffry jennings jens jerad jerald jeramiah jeramie jeramy jered jerel jereme jeremey
jeremiah jeremias jeremie jeremy jerimiah jermaine jermey jermiah jerod jerold jerome jeromy
jeron jerrel jerrell jerrod jerrold jerry jeshua jess jesse jesus jet jethro jett jevon jhon jim
jimmy joaquin job joe joel joeseph joesph johan john johnathan johnathon johnmichael johnny
johnpaul johnson johny jon jonah jonas jonatan jonathan jonathon jones jonny jordy jorge jose
josef joseluis joseph josh joshua joshuah josiah josias josue jovani jovanni jovanny jovany
joziah juan juancarlos judah judd judge judson juelz julian julien julio julius junior junius
justen justin juston justyn juwan kade kadeem kaden kadin kaeden kael kahlil kaiden kain kaine
kaison kale kaleb kalel kalvin kamal kamron kane kannon kareem karim karl kase kasen kash kason
kavin kavon kayleb kayson keandre keanu kedrick keenan keion keith kelton kelvin ken kenan
kendric kendrick kenji kennard kenneth kenney kennith kennth kenny kent kenton kentrell kenyon
keon kermit kerwin keshaun kevan keven kevin kevon keyon keyshawn khalid khalil khristopher kian
kiel kieth king kingston kip kipp kirk kirkland kirt klayton knox kobe koby kody koen kohen kole
kollin kolten kolton konner konnor konrad korbin kraig krish kristofer kristoffer kristopher
kurt kurtis kwame kyan kyle kyren kyron kyson lachlan ladarius lafayette laith lamar lamarcus
lamarr lambert lamont lamonte lance landan landen landin landon lanny laron larry lars lathan
laurence lauro lavar lawerence lawrance lawrence lawson lawton lazaro lazarus leamon leander
leandro leeland leeroy leif leland lemuel len lenard lenwood leo leobardo leon leonard leonardo
leonel leonidas leopold leopoldo leroy les lester levi levy lew lewis lex liam lincoln lino
linton linus linwood lionel lloyd lochlan lon lonny lonzo lorenzo lorne louis lowell loyd luc
luca lucas lucian luciano lucien lucio lucious lucius ludwig luigi luis luiz lukas luke luther
lyle lyman lyndon lynwood mac macario maceo mack maddox magnus mahlon mahmoud major makai makhi
malachi malakai malaki malcolm malcom malek malik malvin manley manny manuel marc marcelino
marcello marcellus marcelo marco marcos marcus marek margarito mariano marino mario marius mark
markeith markel markell marko markus marlon marques marquez marquis marquise marshal marshall
marshawn martell martez martin marvin masen mason massimo mateo mathew mathias mathieu matias
matt matteo matthew matthias maurice mauricio mauro maverick max maxim maximilian maximiliano
maximillian maximo maximus maxton maxwell maxx maynard mcarthur mccoy meir mekhi melton melville
melvin melvyn menachem mendel merton mervin meyer michael micheal mick miguel miguelangel mike
mikeal mikhail milburn miles milford millard milo milton miquel misael mitch mitchel mitchell
modesto mohamad mohamed mohammad mohammed moises monte montrell monty mordechai morris morton
mose moses moshe muhammad murray murry musa mustafa myles myron napoleon narciso nash nasir nat
nathan nathanael nathanial nathaniel nathen nazir neal ned neel nehemiah neil nels nelson nestor
neville nevin newell newton neymar nicholas nicholaus nick nicklas nicklaus nickolas nicolas
nigel nikhil nikolai nikolas nikolaus niles nils nino nixon noah noble noe nolan nolen norbert
norberto norman normand norris norton norval norwood obed octavio octavius odin odis olaf olan
olen olin oliver omar omari omarion omer oneal oran oren orin orion orland orlando orrin orval
orville osbaldo oscar osiel oskar osman osvaldo oswald oswaldo otho otis ottis otto owen pablo
paolo pascal pascual pasquale patric patricio patrick paul paulo pedro percy perry pete peter
phil philip philippe phillip pierce pierre pierson pietro porfirio porter pranav prentice
prentiss preston price prince princeton quentin quenton quinten quintin quinton raekwon rafael
rafe raheem rahul raiden ralph ramiro ramon ramone ramses rance rand randal randall randel
randell randle randolph randy ransom raoul raphael rashaad rashad rashard rasheed rashid raul
ravi ray rayburn rayford raymon raymond raymundo raynard rayshawn reed reggie reginal reginald
reid reinaldo renaldo renard renato reno reuben rex rexford rey reymundo reynaldo reynold rhett
ricardo rich richard richardo richmond rick rickey ricky rico ridge rigoberto rishi ritchie rob
robb robby robert roberto robinson roby rocco rock rocky rod roddy roderic roderick rodger
rodney rodolfo rodrick rodrigo roel rogelio roger rogers rohan rojelio roland rolando rolf
rolland rollie rollin roman romel romeo ron ronald ronaldo ronan rondell ronin ronnie ronny
roosevelt roque roscoe rosendo rosevelt ross rowdy rowland roy ruben rubin rudolf rudolfo
rudolph rudy rueben rufus rupert rush russ russel russell rustin rusty ryan ryder ryker ryne
saad sabastian sahil said sal salomon salvador salvatore sam sameer samir sammuel sammy sampson
samson samual samuel sanders sanford sanjay santiago santino santo saul savion scot scott scotty
seamus sean sebastian sebastien sedrick sergio servando seth seymour shad shamar shane sharif
shaun shedrick sheldon shelton shemar shepherd sherman sherwin sherwood shimon shlomo shmuel sid
siddharth sigmund silas silvestre silvio simeon simon skip slade smith solomon sonny spencer
stafford stan stanford stanley stanton steele stefan stefano stephan stephen stephon stetson
stevan steve steven stewart stone stoney stuart sven syed sylas sylvan sylvester tad tahj talan
talmadge talmage talon tanner tarek tarik tariq taron taurean tavares tavaris tavion tavis tavon
ted teddy teodoro terance terell terence terrance terrel terrell terrence terron tevin thad
thaddeus thane thatcher theadore theodis theodore theophilus theron thiago thomas thompson thor
thornton thurman thurston tillman tim timmothy timmy timothy titan tito titus tobias tobin tod
todd tom tomas tommy toney tony torin trace trae travion travis travon trayvon tre tremayne
trent trenten trenton trever trevin trevion trevon trevor trey treyton treyvon tripp triston
troy truett truman tucker turner ty tyler tyquan tyran tyre tyreek tyrek tyrel tyrell tyrese
tyron tyrone tyrus tyshawn tyson tzvi ubaldo ulises ulysses umar urban uriel urijah valentin
valentino vance varun vaughn vern vernard vernon vic vicente victor vidal vihaan viktor vince
vincent vincente vincenzo vinson virgil virgle vito vladimir wade waldo walker wallace wally
walt walter walton ward wardell warner warren washington watson wayland waylon wayman waymon
wayne webster weldon wellington welton wendall wendel wendell werner wes wesley west westin
westley weston wilber wilbert wilbur wilburn wiley wilford wilfred wilfredo will willam willard
willem william williams willian willis willy wilmer wilson wilton windell winfield winford
winfred winston wm wolfgang woodrow woody worth wyatt wyman xander xavier xzavier yaakov yadiel
yahir yahya yair yakov yandel yash yehuda yisroel yitzchok yoel yonatan yosef yousef youssef
yusef yusuf zach zachariah zachary zachery zack zackary zackery zahir zaid zaiden zain zakary
zamir zander zane zavier zavion zayd zayden zayn zayne zeb zechariah zeke zev
"""

FEMALE = frozenset(_FEMALE.split())
MALE = frozenset(_MALE.split())

#: A label that opens with one of these has no first name to read ("Mr. Bennet", "Lady Lucas").
_NOT_A_NAME = frozenset(
    {"mr", "mrs", "miss", "ms", "mister", "madam", "madame", "lady", "lord", "sir", "dame", "master", "elder",
     "senior", "the", "a", "an"}
)


def name_gender_prior(label: str) -> str | None:
    """`"male"` / `"female"` when the label's first name leans strongly one way in the table, else None."""
    tokens = [t.strip(".,;:'\"()").lower() for t in label.split()]
    if not tokens or tokens[0] in _NOT_A_NAME:
        return None
    if tokens[0] in FEMALE:
        return "female"
    return "male" if tokens[0] in MALE else None
